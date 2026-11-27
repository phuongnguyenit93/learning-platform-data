# Managing Response InputStream Lifecycle in Java 17

When a Java program sends an HTTP request and receives a response as a byte stream, receiving the response object does not mean the entire content has already been read. The application must still consume or close the response stream promptly to release resources, avoid holding connections open, and prevent resource leaks on errors.

In Java 17, the standard way to perform HTTP is with `java.net.http.HttpClient`. With `HttpResponse.BodyHandlers.ofInputStream()`, the response body is provided as an `InputStream`. **The application owns the responsibility for closing this stream** after finishing reading or deciding to discard the remainder.

This lesson focuses on the response body lifecycle, using `try-with-resources`, handling success and error responses, bounded reading, decoding bytes to text with the proper charset, and managing streams in asynchronous pipelines.

## 1. What Parts Does an HTTP Response Have?

An HTTP response can be viewed as consisting of:

- **Status code:** indicates the protocol-level outcome, such as `200`, `404`, or `500`.
- **Headers:** metadata such as `Content-Type`, `Content-Length`, and `Cache-Control`.
- **Body:** the response payload, which may be JSON, text, images, files, or binary content.

In Java 17, `HttpResponse<T>` holds the status, headers, associated request, and body of type `T` chosen by `BodyHandler<T>`.

For example, using `BodyHandlers.ofString()` gives a `String` body; using `BodyHandlers.ofByteArray()` gives a `byte[]` body; using `BodyHandlers.ofInputStream()` gives an `InputStream` body.

~~~java
HttpResponse<String> textResponse =
        client.send(request, HttpResponse.BodyHandlers.ofString());

HttpResponse<byte[]> binaryResponse =
        client.send(request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<InputStream> streamResponse =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());
~~~

These three approaches have different lifecycle characteristics. `String` and `byte[]` are collected into memory by the handler before the response is returned. With `InputStream`, the application receives a stream to read and close itself.

## 2. BodyHandlers.ofInputStream and Stream-Closing Responsibility

`HttpResponse.BodyHandlers.ofInputStream()` is suitable when:

- The body may be large and should not be loaded entirely into RAM.
- You want to read data incrementally.
- You want to pipe the body directly to a file or a streaming parser.
- You want to control reading, limit bytes read, or process content progressively.

Minimal example:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpStreamDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            byte[] firstBytes = body.readNBytes(128);
            System.out.println("Status: " + response.statusCode());
            System.out.println("Read bytes: " + firstBytes.length);
        }
    }
}
~~~

`try-with-resources` ensures `body.close()` is called whether the block finishes normally or exits with an exception. This is the simplest way to guarantee the stream is not forgotten.

Avoid writing:

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

InputStream body = response.body();
byte[] data = body.readAllBytes();
// Forgot body.close()
~~~

If you fail to close the body after use, the application can hold onto resources tied to response delivery longer than necessary. This is especially noticeable when a service handles many requests, large responses, or repeated partial reads that fail mid-stream.

## 3. Resource Lifecycle from Request Dispatch to Body Closure

With `ofInputStream()`, the workflow typically looks like:

~~~text
Create HttpClient / HttpRequest
          |
          v
Send request
          |
          v
Receive status and headers
          |
          v
BodyHandler provides InputStream
          |
          v
Application reads body as needed
          |
          +---- Read full body
          |
          +---- Stop early / encounter error
          |
          v
Close InputStream in all cases
          |
          v
Finish response handling
~~~

The key point is that **the response body has its own lifecycle**. The `HttpResponse` object itself is not a closeable resource; the stream returned by `response.body()` is the resource the application must manage.

Even when the body has been read completely, closing the stream remains an explicit end to its lifecycle. If only part of the body is read, closing the stream signals to the implementation that the application no longer wishes to consume the rest. Whether the implementation reuses the physical connection or discards the connection/stream depends on the protocol and implementation; never rely on a specific assumption to skip closing.

## 4. Using try-with-resources When Reading the Whole Body

If the body is small and has a reliable size bound, you can read it all into a byte array:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class ReadAllBodyDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/data"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            byte[] bytes = body.readAllBytes();
            System.out.println("Status: " + response.statusCode());
            System.out.println("Body size: " + bytes.length);
        }
    }
}
~~~

`readAllBytes()` reads until EOF and allocates an array holding all data. This is easy to use, but consider body size: if the server sends a huge or unbounded payload, the array can consume excessive memory or trigger `OutOfMemoryError`.

`connectTimeout` limits connection establishment time. `HttpRequest.timeout` sets a request deadline per the API contract, but with a body handler returning an `InputStream`, note that stream reading may continue after the response and headers have been handed to the caller. Do not treat request timeout as a resource limit or size limit for the entire body-consumption phase.

## 5. Checking Status Codes While Still Closing the Body

An HTTP status does not automatically turn into an exception when using `HttpClient.send`. A `404` or `500` response is still returned normally. The application must inspect `statusCode()` and decide whether to read the error body or discard it.

Crucially: **whether the status indicates success or failure, once you receive an `InputStream`, you must close it**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class StatusAndBodyDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/items"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            int status = response.statusCode();

            if (status >= 200 && status < 300) {
                byte[] bytes = body.readAllBytes();
                System.out.println("Success, bytes: " + bytes.length);
            } else {
                byte[] errorBytes = body.readNBytes(4096);
                String errorText =
                        new String(errorBytes, StandardCharsets.UTF_8);

                throw new IOException(
                        "HTTP " + status + ": " + errorText);
            }
        }
    }
}
~~~

The error branch reads at most 4096 bytes for diagnostic information, then throws an exception. When the exception exits the `try` block, the stream is still closed.

In real applications, which status codes count as success depends on the API contract. Not every endpoint only uses `2xx`; for instance, some flows treat `304 Not Modified` as a normal outcome. Define policies according to the API you are calling.

## 6. Reading Bodies Incrementally and Bounding Size

When receiving data over the network, never assume the body is small. The `Content-Length` header may be absent, untrusted, or omitted when the transfer mechanism does not know the final length upfront.

To enforce a size cap, you can read up to `MAX_BYTES + 1` bytes. If more than the limit arrives, reject it:

~~~java
import java.io.IOException;
import java.io.InputStream;

static byte[] readAtMost(InputStream input, int maxBytes)
        throws IOException {
    if (maxBytes < 0 || maxBytes == Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Invalid maxBytes");
    }

    byte[] bytes = input.readNBytes(maxBytes + 1);
    if (bytes.length > maxBytes) {
        throw new IOException("Response body exceeds size limit");
    }
    return bytes;
}
~~~

Usage:

~~~java
private static final int MAX_RESPONSE_BYTES = 1_000_000;

try (InputStream body = response.body()) {
    byte[] data = readAtMost(body, MAX_RESPONSE_BYTES);
    process(data);
}
~~~

If the body exceeds the limit, an exception is thrown and `try-with-resources` still closes the stream. This approach reads at most one byte past the threshold to detect oversized bodies; the remainder is left unconsumed.

For large bodies that must be processed completely, read using a buffer and count total bytes with a `long`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

static byte[] readBounded(InputStream input, long maxBytes)
        throws IOException {
    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must be non-negative");
    }

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] buffer = new byte[8192];
    long total = 0;

    int count;
    while ((count = input.read(buffer)) != -1) {
        total += count;
        if (total > maxBytes) {
            throw new IOException("Response body exceeds size limit");
        }
        output.write(buffer, 0, count);
    }

    return output.toByteArray();
}
~~~

This example still keeps the entire body in RAM, so it is only suitable when the limit is small enough. For large payloads, write each buffer directly to a file or process it incrementally instead of accumulating into a `ByteArrayOutputStream`.

## 7. Streaming the Body Directly to a File

When downloading files, avoid loading the entire response into a `byte[]`. You can copy the stream to a file using buffered I/O:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class DownloadDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/archive.bin"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        Path destination = Path.of("archive.bin");

        try (InputStream body = response.body()) {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " + response.statusCode());
            }

            Files.copy(
                    body,
                    destination,
                    StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
~~~

`Files.copy(InputStream, Path, ...)` reads the stream until EOF or error. `try-with-resources` is still needed to close the body after copying completes or fails.

When downloading important files, write to a temporary file first and rename it only after download and validation succeed. This avoids leaving behind a destination file that looks complete but actually holds partial data. Also enforce size limits, check checksums/signatures if required by the protocol, and handle out-of-disk-space conditions.

## 8. Decoding the Response Body to Text with the Right Charset

HTTP bodies are bytes. If the content is text, the application must know the charset from the response contract, commonly declared in `Content-Type`, such as `text/plain; charset=UTF-8`.

When the API specifies UTF-8, use `StandardCharsets.UTF_8`:

~~~java
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

try (InputStream body = response.body();
     BufferedReader reader = new BufferedReader(
             new InputStreamReader(body, StandardCharsets.UTF_8))) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

Here both `body` and `reader` are declared in try-with-resources. `BufferedReader.close()` closes the underlying reader and stream; declaring both can cause the stream to be closed twice. `InputStream.close()` is generally designed to be idempotent, though you can write it more concisely by managing only the reader:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                response.body(),
                StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
~~~

The reader owns the wrapped stream and closes it when finished.

If the charset is supplied by the server and the application must follow the header, parse `Content-Type` per API policy. Do not use the client machine's `Charset.defaultCharset()` as the default charset for a protocol with a defined encoding.

## 9. Different BodyHandlers and Their Lifecycle Consequences

`HttpResponse.BodyHandlers` offers several options. Choose based on size and how the body is consumed:

| Body handler | Body type | Lifecycle characteristics |
| --- | --- | --- |
| `ofString()` | `String` | Handler reads the body and creates a string before the response completes; no stream for caller to close. |
| `ofByteArray()` | `byte[]` | Reads the entire body into RAM; fits small, bounded payloads. |
| `ofInputStream()` | `InputStream` | Caller reads and must close the stream. Fits streaming or large bodies. |
| `ofFile(path)` | `Path` | Handler writes the body to a file; caller manages the file after response completes. |
| `discarding()` | `Void` | Discards the body when content is unneeded. |

### 9.1. Using ofString

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());

System.out.println(response.body());
~~~

There is no body stream to close because the body is a `String`. However, all content is held in memory; do not use this for responses that may be very large.

If you need to specify a charset:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

### 9.2. Using ofByteArray

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

byte[] body = response.body();
~~~

The body is collected into an array. The caller has no stream to close, but must control response size to avoid unbounded memory usage.

### 9.3. Using ofFile

~~~java
HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(Path.of("download.bin")));
~~~

The handler writes content to the file and the response body is the path. Internal file stream resources are managed by the handler; afterward, the application is responsible for managing the created file, including deleting temporary files if processing fails or the data is invalid.

### 9.4. Using discarding

If you only need the status/headers and not the body:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding());
~~~

The handler actively discards the body instead of handing a stream to the caller. This is the clearer choice when the application does not need the response content.

## 10. Closing Streams on Exceptions or Partial Reads

Resource lifecycles must hold across both success and failure paths. Errors that can occur during reading include:

- The server closes the connection before sending the complete body.
- Network interruption.
- Malformed data.
- Parser throws an exception.
- Application decides to abort because the body is too large.
- Target file is unwritable or disk is full.

`try-with-resources` closes the stream even when the block body throws an exception:

~~~java
try (InputStream body = response.body()) {
    byte[] data = body.readNBytes(4096);
    parse(data); // Even if parse throws an exception, body is still closed.
}
~~~

Never close the stream only at the end of the happy path:

~~~java
InputStream body = response.body();
byte[] data = body.readAllBytes();
parse(data);
body.close(); // Not reached if readAllBytes or parse throws an exception.
~~~

If legacy APIs prevent using try-with-resources, use `finally` to close. In Java 17, however, try-with-resources is usually clearer and less error-prone.

## 11. sendAsync and Managing Bodies Asynchronously

`HttpClient.sendAsync()` returns a `CompletableFuture`. With `ofInputStream()`, the future completes when the response body handler supplies `HttpResponse<InputStream>`; reading the stream can happen afterward.

Example:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;

public class AsyncStreamDemo {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/data"))
                .GET()
                .build();

        CompletableFuture<HttpResponse<InputStream>> future =
                client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofInputStream());

        future.thenAccept(response -> {
            try (InputStream body = response.body()) {
                byte[] data = body.readAllBytes();
                System.out.println("Status: " + response.statusCode());
                System.out.println("Bytes: " + data.length);
            } catch (Exception e) {
                System.err.println("Could not read response: " + e);
            }
        });
    }
}
~~~

Things to keep in mind:

- Once the future completes and yields a response, the caller assumes responsibility for closing `response.body()`.
- If processing the body asynchronously, the stream must be closed within that callback or the component taking ownership of the stream.
- Do not pass the stream outward without defining who owns and closes it.
- If the callback never runs because the future was cancelled or failed before yielding a response, there is no body stream for the caller to close.
- If the callback receives a response but skips processing it, the body must still be closed.

### 11.1. Avoid blocking stream reads on completion threads

Reading an `InputStream` can block the thread until bytes or EOF arrive. If a callback runs on the thread used to complete the future, performing a long read or heavy work inside the callback can affect other tasks.

Offload processing to a dedicated executor:

~~~java
ExecutorService bodyExecutor = Executors.newFixedThreadPool(4);

CompletableFuture<Void> processing = future.thenAcceptAsync(response -> {
    try (InputStream body = response.body()) {
        processStream(body);
    } catch (IOException e) {
        throw new UncheckedIOException(e);
    }
}, bodyExecutor);
~~~

In real applications, the executor also has its own lifecycle and must be managed and shut down via its API. Do not create a new executor per request and leak it. Also handle exceptions on the `CompletableFuture` at the call site so errors do not go unnoticed.

## 12. Cancelling Requests and Cancelling Body Reads

Cancelling a `CompletableFuture` or stopping waiting for a result does not mean every associated resource is automatically released at every point. Distinguish:

1. **Before a response arrives:** the request/future can be cancelled; the implementation handles stopping the exchange as supported by the protocol.
2. **After receiving a response with an InputStream:** the caller owns the stream and must close it when no longer reading.
3. **Mid-read:** closing the stream signals the end of body consumption; the read call may finish with EOF or an exception depending on transfer state.

If your application has its own deadline or cancellation token, pass cancellation state into the reader layer and ensure the cancellation branch closes the stream. Never simply drop references to the body and expect the garbage collector to close resources promptly.

## 13. Timeouts: Connect, Request, and Stream Reading

Java 17 `HttpClient` provides several timeout settings:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(15))
        .GET()
        .build();
~~~

Distinguish:

| Setting | Meaning |
| --- | --- |
| `HttpClient.Builder.connectTimeout(...)` | Limits connection establishment time. |
| `HttpRequest.Builder.timeout(...)` | Deadline for the request per API contract; exceeding it can result in `HttpTimeoutException`. |
| Application body-reading deadline | Caps total time or wait duration during the stream consumption phase; must be designed at the application layer if specific rules are needed. |

With `ofInputStream()`, the response may be delivered to the caller before the caller finishes reading the body. Thus, do not treat request timeout as a byte-size limit or as a sole guarantee that every subsequent `InputStream.read()` will complete within the same window.

If a body can take a long time, combine size limits, business deadlines, cancellation, and stream closing. For very specific per-read timeout requirements, consider a suitable streaming/`BodySubscriber` architecture instead of relying on a single timeout.

## 14. Does HttpClient Need to Be Closed Like InputStream?

In Java 17, `HttpClient` does not implement `AutoCloseable` and does not have a `close()` method like the APIs added in newer JDK releases. Therefore, do not write:

~~~java
try (HttpClient client = HttpClient.newHttpClient()) {
    // Invalid against the Java 17 API.
}
~~~

Typically, create one `HttpClient` and reuse it across multiple requests instead of creating a new client per request. The client is immutable and shareable across requests; reusing it also enables the implementation to manage connection pooling effectively.

This does not change your responsibility to close body streams. In Java 17:

- Reuse `HttpClient`.
- Close the body `InputStream` returned by `ofInputStream()`.
- Close files, readers, writers, or other resources opened directly by the application.
- Do not attempt to call `close()` on `HttpClient` from newer Java versions when targeting Java 17.

## 15. Reading the Body While Checking Content-Length

The `Content-Length` header can help the application reject oversized responses early:

~~~java
long declaredLength = response.headers()
        .firstValueAsLong("Content-Length")
        .orElse(-1L);

if (declaredLength > MAX_RESPONSE_BYTES) {
    try (InputStream body = response.body()) {
        // Close the body immediately because this payload is rejected.
    }
    throw new IOException("Response is too large");
}
~~~

However, never rely solely on `Content-Length`:

- The header may be missing.
- The value may be untrustworthy.
- The body transfer mode may not provide the length upfront.
- Actual bytes read still need to be counted while reading.

Use the header as an early check, and still enforce a limit on actual bytes read. If rejecting a response after receiving its body stream, close the stream before exiting.

## 16. Handling Read Errors and Distinguishing HTTP Errors from Transport Errors

There are two different error categories:

**HTTP-layer errors:** the server returns a status like `400`, `401`, `404`, or `500`. This is still a valid HTTP response; the caller inspects the status and decides whether to read the error body.

**Transport/read-layer errors:** DNS failure, connection refused, timeout, dropped connection, or stream read failure. These cases can throw `IOException`, `HttpTimeoutException`, or related exceptions.

Example:

~~~java
try {
    HttpResponse<InputStream> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofInputStream());

    try (InputStream body = response.body()) {
        if (response.statusCode() != 200) {
            throw new IOException(
                    "Unexpected status: " + response.statusCode());
        }
        processStream(body);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IOException("HTTP request was interrupted", e);
}
~~~

If the thread is interrupted while waiting for `send`, restore the interrupt status with `Thread.currentThread().interrupt()` before propagating the exception or finishing. Never swallow `InterruptedException` and keep executing as if no cancellation was requested.

## 17. Common Resource-Management Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting to close `response.body()` | Holds transport resources longer than needed | Use try-with-resources. |
| Closing the stream only at the end of the success path | Exceptions can skip the close call | Wrap the stream in try-with-resources immediately upon receiving the response. |
| Reading an error body without closing | Resources stay held when the server returns an error status | Close the body in error branches as well. |
| Calling `readAllBytes()` on unbounded bodies | May consume excessive RAM | Enforce limits or stream via buffers/files. |
| Abandoning the stream after partial reads | Remaining body stays unconsumed | Close the stream as soon as you decide to stop. |
| Passing the stream to another callback without transferring ownership | Unclear which component must close it | Define ownership clearly and close in the receiving callback. |
| Using the default charset to read text bodies | Content may corrupt across environments | Follow `Content-Type`/API contract and specify the charset. |
| Assuming Java 17 `HttpClient` must be closed like a stream | Using APIs absent in Java 17 | Reuse the client; close response bodies and app-owned resources. |
| Trusting `Content-Length` exclusively | Cannot bound bodies when the header is missing or wrong | Count actual bytes while reading. |
| Swallowing `InterruptedException` | Loses cancellation signal from the managing thread | Restore interrupt status or propagate the exception. |

## 18. Implementation Pattern: Reading a Bounded JSON Response with Proper Lifecycle

The following example combines status checks, size bounds, UTF-8 decoding, and body closure:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class BoundedJsonClient {
    private static final int MAX_BODY_BYTES = 1_000_000;

    private final HttpClient client;

    public BoundedJsonClient() {
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    public String getJson(URI uri)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            if (response.statusCode() < 200
                    || response.statusCode() >= 300) {
                byte[] errorBytes = body.readNBytes(4096);
                String error = new String(
                        errorBytes,
                        StandardCharsets.UTF_8);
                throw new IOException(
                        "HTTP " + response.statusCode() + ": " + error);
            }

            byte[] bytes = body.readNBytes(MAX_BODY_BYTES + 1);
            if (bytes.length > MAX_BODY_BYTES) {
                throw new IOException("JSON response exceeds size limit");
            }

            return new String(bytes, StandardCharsets.UTF_8);
        }
    }
}
~~~

The class retains a single `HttpClient` for reuse. Each call to `getJson` receives a new response body stream; the try-with-resources block ensures that stream is closed whether the status is an error, the body is too large, or processing succeeds.

The example assumes the endpoint returns UTF-8 JSON. In real systems, validate `Content-Type`, charset policy, JSON schema, and accepted status codes. If the body exceeds the limit, the code rejects it after reading at most one extra byte to detect the overflow.

## 19. Self-Check Questions

**1. With `BodyHandlers.ofInputStream()`, who is responsible for closing the body stream?**  
The caller receiving `HttpResponse<InputStream>` is responsible for closing `response.body()` after reading finishes or stops.

**2. Why should you use try-with-resources?**  
Because the stream is closed whether the block completes normally or exits via an exception.

**3. Is `HttpResponse` a resource requiring `close()`?**  
No. For an `InputStream` body, the resource that must be closed is the stream returned by `response.body()`.

**4. Does HTTP status 404 cause `HttpClient.send` to throw an exception automatically?**  
No. It normally returns a response with status 404; the application must check the status and handle the body.

**5. When are `ofString()` or `ofByteArray()` a better fit than `ofInputStream()`?**  
When the body is small, bounded, and you want the already-collected payload; they do not hand a body stream to the caller.

**6. Why should you avoid `readAllBytes()` on unbounded bodies?**  
Because the entire body is retained in RAM and can cause memory pressure or `OutOfMemoryError`.

**7. What should you do if you only read part of a body and then stop?**  
Close the stream as soon as you decide to stop; do not leave the stream open.

**8. Can you rely solely on Content-Length to limit response size?**  
No. The header may be absent or untrustworthy; you must limit the actual number of bytes read.

**9. With `sendAsync` and `ofInputStream`, when does the caller close the stream?**  
Once the future yields a response and the callback/consumer takes ownership of the body; close the stream inside that component.

**10. Does Java 17 `HttpClient` require try-with-resources?**  
No. `HttpClient` in Java 17 does not implement `AutoCloseable`; reuse the client and manage body streams separately.

**11. Is `HttpRequest.timeout` a body size limit?**  
No. Timeout and byte limit are separate policies; the application must enforce size limits while reading.

**12. Why specify a charset when reading text responses?**  
Bodies are bytes; the charset must match the API contract to decode accurately instead of depending on the machine's default charset.

## Official References

- [Java SE 17 API — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): sending synchronous/asynchronous requests and configuring the client.
- [Java SE 17 API — `HttpResponse`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): response status, headers, and body.
- [Java SE 17 API — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): body handlers such as `ofString`, `ofByteArray`, `ofInputStream`, `ofFile`, and `discarding`.
- [Java SE 17 API — `InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): reading bytes, `readNBytes`, `readAllBytes`, `transferTo`, and closing streams.
- [Java SE 17 API — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): copying streams to files and managing files.
- [Java SE 17 API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charsets for decoding text.
