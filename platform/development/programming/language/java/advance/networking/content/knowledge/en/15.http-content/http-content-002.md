# Java HttpClient: Sending String, byte[], File, and InputStream with BodyPublishers

## 1. Context and Objectives

When calling an HTTP API from Java, the **request body** can be JSON text, a binary byte array, file contents on disk, or data that can only be read sequentially from an `InputStream`. In Java 17+, `java.net.http.HttpClient` provides `HttpRequest.BodyPublishers` to describe **the bytes to be sent** without forcing every kind of data source to be converted into a `String` or byte array on the heap.

The four core options covered in this lesson:

~~~java
HttpRequest.BodyPublishers.ofString(text, StandardCharsets.UTF_8)
HttpRequest.BodyPublishers.ofByteArray(bytes)
HttpRequest.BodyPublishers.ofFile(path)
HttpRequest.BodyPublishers.ofInputStream(streamSupplier)
~~~

These are **illustrative expressions**; they need to be placed inside a method where `text`, `bytes`, `path`, and `streamSupplier` are declared. Each expression returns an `HttpRequest.BodyPublisher` that can be passed to `POST(...)` or `method("PUT", publisher)`. The key differences lie in **the byte source, encoding, whether the size is known in advance, when reading occurs, and whether it can be resent**.

After this lesson, you will be able to: choose the right publisher for String/byte[]/file/InputStream; declare an appropriate `Content-Type`; understand `contentLength()`, UTF-8, and request framing; implement uploads without reading the entire file into RAM; handle stream suppliers safely; distinguish between a request `BodyPublisher` and a response `BodyHandler`; and run a Java 17+ demo sending all four types to a loopback HTTP server.

## 2. Overview of HTTP Request Body and BodyPublisher

An HTTP request has a **request line/method**, **headers**, and a **body**. For example:

~~~http
POST /messages HTTP/1.1
Host: api.example.test
Content-Type: application/json; charset=utf-8
Content-Length: 23

{"message":"hello Java"}
~~~

`Content-Length: 23` is just an example calculated in **bytes** for the illustrative ASCII body snippet, not a value you always have to write manually. When sending a String with Vietnamese characters or emoji, **the number of Java characters and the number of UTF-8 bytes can differ**. `Content-Type` states what format the body is in; `Content-Length` (if present) states the number of bytes on the wire. Neither can be reliably guessed by the server solely from the `String` content.

Java `HttpClient` flow:

~~~text
               Java application
                      |
                      | create HttpRequest
                      v
HttpRequest.BodyPublisher (String / byte[] / File / InputStream)
                      |
                      | provide ByteBuffer per Flow.Publisher contract
                      v
                 HttpClient
                      |
                      | HTTP framing: HTTP/1.1 or HTTP/2
                      v
               HTTP request bytes
                      |
                 Network / TLS
                      v
                 HTTP server
                      |
               read request body
                      v
                 send response
                      |
                      v
HttpResponse.BodyHandler<T> -> response body T
~~~

`BodyPublisher` **publishes the request body**, not a response parser/reader. For **incoming** data, the client uses `BodyHandlers.ofString()`, `ofByteArray()`, `ofFile()`, `ofInputStream()`, etc., with different semantics. The two API groups often share similar names, but **the data flows in opposite directions**.

### 2.1. Building a Request Does Not Necessarily Send Any Bytes Yet

~~~java
HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/upload"))
        .header("Content-Type", "text/plain; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8))
        .build();

// client.send() or client.sendAsync() has not been called yet:
// the request is configured, no network request is created by build() alone.
~~~

The code above is an **illustrative snippet** (requires importing `java.net.URI`, `java.net.http.HttpRequest`, and `java.nio.charset.StandardCharsets`). `HttpRequest` describes the method/URI/headers/body; `HttpClient.send(...)` or `sendAsync(...)` is what actually performs the transmission.

Specifically with a file or InputStream, creating a BodyPublisher **does not mean all the content has already been read**. This is an important benefit for large data, but it also requires **keeping the data source available until the request actually completes**.

## 3. Quick Selection Table for the Four BodyPublisher Types

| Body source | API | Byte source | Typical `contentLength()` | Use case |
| --- | --- | --- | --- | --- |
| `String` | `BodyPublishers.ofString(text, charset)` | Encode String using charset | **Known in advance** after encoding | Small/medium JSON, text, XML |
| `byte[]` | `BodyPublishers.ofByteArray(bytes)` | Binary bytes already in RAM | **Known in advance** by byte count | Protobuf, already-generated images/binary bytes |
| `Path` file | `BodyPublishers.ofFile(path)` | File contents on filesystem | **Usually known** from file size | Upload a large file without `readAllBytes` |
| `InputStream` supplier | `BodyPublishers.ofInputStream(supplier)` | Stream opened by supplier when publisher needs it | **-1**, meaning unknown in advance | Data generated incrementally or streamed from another source |

**Limitation:** the “known in advance” cells describe `BodyPublisher.contentLength()`, **not a guarantee that a specific Content-Length header will appear in every HTTP version**. With HTTP/1.1, an unknown-length body may use chunked transfer coding; with HTTP/2, payloads travel in DATA frames with different framing rules. Let `HttpClient` manage wire framing; do not manually set `Transfer-Encoding`/`Content-Length` to force an inappropriate result.

In this lesson, small Strings and byte[] can use in-memory data; large files should use `ofFile`; when you only have a streaming source/generator and **can supply a new stream when needed**, use `ofInputStream`.

## 4. `BodyPublishers.ofString`: Sending Text and Choosing a Charset

### 4.1. Two Common Overloads

~~~java
HttpRequest.BodyPublisher a =
        HttpRequest.BodyPublishers.ofString("Hello");
// Defaults to UTF-8 in the overload without a charset argument.

HttpRequest.BodyPublisher b =
        HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8);
// Explicitly specify the charset to avoid encoding misunderstandings.
~~~

The illustrative code requires importing `java.net.http.HttpRequest` and `java.nio.charset.StandardCharsets`. `ofString` converts a String to bytes using the chosen charset. The client itself does not infer the `Content-Type` header just because the publisher receives a String; **you must declare the media type required by the API contract**.

Example sending JSON:

~~~java
String json = "{\"name\":\"Mai\",\"active\":true}";

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/users"))
        .header("Content-Type", "application/json; charset=utf-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

This is an **illustrative snippet without `main`**; it requires importing `java.net.URI` and `HttpRequest`. `Content-Type` describes **the request body you send**; `Accept` describes **the representations you want in the response**. The two headers do not replace each other.

### 4.2. Character Count Does Not Equal UTF-8 Byte Count

~~~java
String text = "Xin chào";
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
System.out.println(text.length());      // 8 UTF-16 code units.
System.out.println(encoded.length);     // 9 UTF-8 bytes.
~~~

The letter `à` occupies one UTF-16 code unit but **two UTF-8 bytes**. If the server/client enforces a 10 KiB limit or a protocol requires the payload length, you must use **the byte length**, not `text.length()` as the byte count. Emoji often have even more UTF-16 code units and different UTF-8 byte counts.

In the runnable demo in section 9, we write the letter `à` using the Java escape `\u00e0` so the output string remains **“Xin chào”**, while avoiding encoding dependencies when copying code across some shells/terminals.

### 4.3. Pros/Cons of ofString

**Suitable for:** pre-built text request bodies such as JSON, a pre-serialized form, XML, or plain text. Readable API with minimal boilerplate.

**Keep in mind:** the String must reside in memory and the publisher encodes it into bytes; if the JSON/text is very large and there are many concurrent requests, high peak memory usage can easily occur. For incrementally generated content, consider an InputStream supplier or publishing byte chunks; do not try to concatenate gigabytes into a single String.

Do not manually concatenate JSON strings by interpolating user data without escaping; use a proper JSON serializer and validate the schema. `ofString` only encodes **text to bytes**, it does not guarantee valid JSON or prevent injection.

## 5. `BodyPublishers.ofByteArray`: When You Already Have Binary Bytes

### 5.1. Sending a Byte Array Intact

~~~java
byte[] payload = {0x00, 0x01, (byte) 0xFF, 0x7F};

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/binary"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();
~~~

The illustrative code requires importing `java.net.URI`/`HttpRequest`. `(byte) 0xFF` has the value `-1` in Java's signed `byte` type, but **preserves the `FF` byte bits when sent**. Do not convert arbitrary binary data into a String if there is no actual text encoding; doing so can lose information or replace invalid bytes.

**Publisher length = number of bytes**. The example above has 4 bytes, `contentLength() == 4`. Unlike `String`, there is no charset encoding step when you already have the exact bytes.

### 5.2. Sending Only a Slice

If you want to send a segment of an array:

~~~java
byte[] all = {9, 8, 7, 6, 5, 4};

// Send three bytes starting at offset=2: {7,6,5}.
HttpRequest.BodyPublisher portion =
        HttpRequest.BodyPublishers.ofByteArray(all, 2, 3);
~~~

**`offset` is the starting position**, `length` is **the number of bytes to send**, not the ending index. The snippet above has `contentLength()==3`. Make sure offset/length are within array bounds; if the parameters are invalid, the API will throw an error rather than guessing the byte range.

### 5.3. Mutable Arrays and Resending

A `byte[]` array is a mutable object. When working with a publisher/request that may be sent asynchronously or across threads, **do not mutate the array contents** while building and transmitting the body. If the source is being updated by another thread, create a controlled snapshot or synchronize at the application layer to ensure the bytes actually sent match what was intended.

Do not assume whether the publisher stores a reference or copies the array as something you can rely on as a business contract. What matters is that the body **must remain consistent** throughout a send, and the application must not introduce unsynchronized mutable state into the I/O path.

### 5.4. When Not to Use ofByteArray?

You should not call `Files.readAllBytes(hugeFile)` and then `ofByteArray(...)` just to upload a large file if you do not need to process the entire file in RAM. That makes heap size/peak memory grow with file size and can cause OOM when there are many concurrent uploads. Use `ofFile(path)` or a stream publisher when the data does not need to be loaded all at once.

## 6. `BodyPublishers.ofFile`: Sending File Contents Directly

### 6.1. Simple Syntax

~~~java
Path path = Path.of("reports", "daily.csv");

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/upload"))
        .header("Content-Type", "text/csv; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofFile(path))
        .build();
~~~

The code above is an **illustrative snippet** inside a method that can throw `IOException`/`FileNotFoundException`, and requires importing `java.nio.file.Path`. `ofFile` creates a publisher that reads bytes from **the file's contents**, instead of you having to call `Files.readAllBytes(path)` first. This is a sensible approach for uploading large files with a better memory footprint.

**Does not mean multipart:** `ofFile(path)` sends **the raw bytes of the file** as the request body. It does not automatically generate `multipart/form-data`, nor does it add `Content-Disposition`, filename, or boundary. A server API expecting multipart must receive a proper multipart structure (usually using an HTTP library with multipart support or packaging it according to spec), not just changing the header to `multipart/form-data`.

### 6.2. File Lifecycle and Errors

- The path must point to a **readable file**, not an unvalidated filename entered by a user.
- `ofFile(path)` can fail early if the file does not exist or is unreadable; if the file loses permissions, is moved, has its contents modified, or encounters an I/O error **during transmission**, the send can also fail.
- Keep the file contents **stable throughout the request**, especially when the server relies on a hash/signature/Content-Length. Do not modify or truncate the file concurrently with the upload and expect the client to keep sending a consistent snapshot.
- For files created by the application to be sent, only clean up/delete them **after the request has completed** (including async requests). Deleting the file right after `request.build()` can leave the body missing when the client needs to read it.
- `Files.size(path)` only reflects the state at the time of the check; do not use it to manually write a `Content-Length` header separate from the publisher mechanism.
- Do not use a `Path` from an untrusted source to allow reading sensitive files on the server/client. Whitelist directories and check symlinks/traversal according to security policy.

### 6.3. Sending a File with PUT

~~~java
Path file = Path.of("uploads", "data.bin");

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/files/data.bin"))
        .header("Content-Type", "application/octet-stream")
        .method("PUT", HttpRequest.BodyPublishers.ofFile(file))
        .build();
~~~

`POST` is a common choice, but BodyPublisher **does not decide the HTTP method**. For an endpoint using `PUT`, you can use `PUT(publisher)` or `method("PUT", publisher)`. For `PATCH` (if the API supports it), use `method("PATCH", publisher)`. POST/PUT/PATCH semantics and idempotency/conditional writes belong to the server protocol, **not to ofFile**.

### 6.4. MIME Type: Not Automatically Inferred from File Extension

If a `.png` file contains an image, you need to set the right media type such as `image/png` per the API contract; if a `.csv` file, typically `text/csv` with an appropriate charset. `ofFile` **does not automatically know the endpoint's expected media type** just from the file extension; setting the `Content-Type` HTTP header is the caller's responsibility.

Do not fully trust user-supplied extensions for upload validation. The server must enforce size limits, authenticate, inspect actual content types, and scan per policy because `Content-Type` is metadata that a client can spoof.

## 7. `BodyPublishers.ofInputStream`: Opening a Stream When Needed for Sending

### 7.1. Why Does the API Take a Supplier Instead of an InputStream?

Conceptual signature:

~~~java
BodyPublishers.ofInputStream(Supplier<? extends InputStream> supplier)
~~~

Instead of passing **an already-opened stream**, you pass a **function that creates/provides a new stream** when the publisher starts a subscription/send. This is necessary because the HTTP client may have to **re-subscribe** to the body in certain situations such as authentication, redirects, or retries depending on policy; a stream that has already been read cannot usually be rewound.

Example emitting bytes from memory via a stream:

~~~java
byte[] data = "stream-body".getBytes(StandardCharsets.UTF_8);

Supplier<InputStream> supplier =
        () -> new ByteArrayInputStream(data);

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(supplier);
~~~

The code above requires importing `java.io.ByteArrayInputStream`, `java.io.InputStream`, and `java.util.function.Supplier`. **Each time the supplier is invoked**, it creates a new `ByteArrayInputStream` positioned at the start; this illustrates the **repeatability/replayability** requirement. In cases where there is only a single live socket stream that cannot be reopened, retrying the body may not be possible.

### 7.2. Using an InputStream from a File or Incremental Source

Example supplier opening a fresh file stream each time:

~~~java
Path file = Path.of("uploads", "large.log");

Supplier<InputStream> supplier = () -> {
    try {
        return Files.newInputStream(file);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(supplier);
~~~

This is an **illustrative snippet inside a method**, requiring imports for `java.io.*`, `java.nio.file.*`, and `java.util.function.Supplier`. Because `Supplier.get()` does not declare checked exceptions, when `Files.newInputStream` throws `IOException` we wrap it in `UncheckedIOException`; otherwise the program **will not compile**.

A stream supplier can be backed by a file, a byte stream generated by another process, or a reopenable source. **Do not return an already-consumed or closed stream** for a subsequent subscription; and do not return `null` to pretend the body is empty, because the publisher cannot obtain a valid data source.

### 7.3. `contentLength() == -1` and Chunked Transfer

With `BodyPublishers.ofInputStream(...)`, the size is typically **unknown in advance**, so `contentLength()` returns **`-1`**, meaning *unknown content length*. That does **not** mean the body has minus one byte or has no body.

The client chooses the appropriate framing mechanism:

- **HTTP/1.1:** an unknown-size body can be sent using `Transfer-Encoding: chunked`, depending on client capabilities and request conditions.
- **HTTP/2:** the body is encapsulated in DATA frames per HTTP/2 rules; HTTP/1.1 chunked transfer coding is not used.
- **Both:** the application should not manually set `Transfer-Encoding` or `Content-Length` inconsistent with the publisher; let the library orchestrate framing.

Some older servers/proxies or endpoints that sign requests with a fixed `Content-Length` require knowing the length in advance. If the body has an unknown size, you need to negotiate compatibility or use a length-known approach (`ofByteArray`, `ofFile`) as required, rather than guessing.

### 7.4. A Supplier Does Not Guarantee Retries

Even if a supplier can open a new stream, **HttpClient does not promise to automatically retry every failure**. It may be impossible to retry a partially sent request, impossible to know whether the server already executed side effects, or another policy may disallow retries.

If the request is `POST /payments` or creates a resource with side effects, resending the entire body after a timeout can **create two transactions**. When safe retries are needed, use an idempotency key/request identifier, timeouts, and transaction semantics defined by the API. Being able to replay a body is a **technical prerequisite**, not a guarantee that the request is **business-idempotent**.

### 7.5. Blocking in the Supplier and Resource Management

`InputStream.read()` can block when the source has no data yet. Even if the caller uses `sendAsync`, the publisher may need a worker to read the stream; code in the supplier/stream can still block. Avoid putting dangerous or indefinitely long operations in the supplier, and design appropriate timeouts, cancellation, and lifecycle handling.

Do not open a stream once outside the supplier and call `ofInputStream(() -> alreadyOpenStream)`: the next call will return the same stream at EOF, or multiple operations will accidentally share the cursor. Return a **fresh stream** for each subscription whenever the source allows.

If the stream is a resource managed by another subsystem and must not be closed, you need a wrapper/publisher with a clear lifecycle contract; do not assume every HttpClient implementation always closes your stream at a fixed point. For normal resources, use a supplier with proper lifecycle management and handle failures/cancellation.

## 8. HTTP Method, Headers, Length, and Response: Putting the Pieces Together

### 8.1. POST, PUT, PATCH, and DELETE

~~~java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofString(
                "{\"ok\":true}", StandardCharsets.UTF_8);

HttpRequest post = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json")
        .POST(body)
        .build();

HttpRequest put = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json")
        .PUT(body)
        .build();

HttpRequest patch = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json")
        .method("PATCH", body)
        .build();

HttpRequest deleteNoBody = HttpRequest.newBuilder(uri)
        .DELETE()
        .build();
~~~

This is an **illustrative snippet**, assuming `uri` is already declared. A publisher can be used for multiple requests if it has suitable subscription semantics, but that does **not** mean every endpoint accepts the same body/method. `DELETE()` has no request body by default; use `BodyPublishers.noBody()` when an empty body is needed for other methods.

### 8.2. `Content-Type` Is Not Automatically Inferred by BodyPublisher

A request sending bytes could be JSON, protobuf, an image, a zip, or text. A `byte[]` alone does not indicate its media type. Therefore:

~~~java
HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

Make sure `Content-Type` **matches the actual bytes**. Sending UTF-8 while advertising `charset=iso-8859-1` is a metadata bug; the server may decode it incorrectly. Sending a PNG file with `Content-Type: text/plain` can cause validation failures or create risks if the server/client sniffs the content.

### 8.3. `BodyPublisher.contentLength()` Is Only Byte-Count Metadata

Example that can be verified in Java:

~~~java
int byteCount = "Xin chào".getBytes(StandardCharsets.UTF_8).length;
// byteCount = 9

HttpRequest.BodyPublisher p =
        HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8);
// p.contentLength() returns 9 for this String.
~~~

When `contentLength() >= 0`, the publisher knows how many bytes it will publish. When it is `-1`, the length is unknown in advance. **Do not** manually add a mismatched `Content-Length` header, as that can cause the request to fail, hang on the server, or violate framing.

For binary data, length is the **byte count**, not the number of Unicode characters or records. For `ofFile`, length is tied to the file's contents; modifying the file mid-send can make the content and length inconsistent.

### 8.4. Response BodyHandler Is a Different API

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

int status = response.statusCode();
String responseBody = response.body();
~~~

Here `BodyHandlers.ofString(...)` **reads the response**. It does not affect whether the request body is published with `ofFile` or `ofInputStream`. Meanwhile, `BodyHandlers.ofByteArray()` reads a binary response, `BodyHandlers.ofFile(path)` saves the response to a file, and `BodyHandlers.ofInputStream()` returns a response InputStream for the caller to read and close per API instructions.

The similarly named APIs `ofString` and `ofFile` in opposite directions are easy to confuse. Look at the full types: `HttpRequest.BodyPublishers` (sending) versus `HttpResponse.BodyHandlers` (receiving).

## 9. Complete Java 17+ Demo: Sending All Four Types to a Loopback HTTP Server

The following program needs no external API. It creates an **HTTP server on `127.0.0.1` and a random port**, then `HttpClient` sends four POSTs:

1. String `"Xin chào"` using UTF-8, which is **9 bytes**.
2. byte[] containing 4 binary bytes: `00 01 FF 7F`.
3. A temporary file containing ASCII `file-body`, **9 bytes** long.
4. An `InputStream` supplier creating a stream containing ASCII `stream-body`, **11 bytes** long; `contentLength()==-1` because the publisher does not know it in advance.

The server replies with the method name, path, actual byte count received, and `Content-Type`. It **does not print raw binary** to avoid garbled characters. This is an educational demo running entirely on loopback. In production, **do not read the entire request body with an unbounded `readAllBytes()`**; enforce max upload size, streaming parsing, and timeouts.

Save as **BodyPublisherDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Supplier;

public class BodyPublisherDemo {
    static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            // Only use readAllBytes because the demo receives tiny payloads.
            byte[] data = exchange.getRequestBody().readAllBytes();
            String contentType = exchange.getRequestHeaders()
                    .getFirst("Content-Type");

            String answer = exchange.getRequestMethod()
                    + " " + exchange.getRequestURI().getPath()
                    + " bytes=" + data.length
                    + " type=" + contentType;

            byte[] response =
                    answer.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, response.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(response);
            }
        }
    }

    static void post(HttpClient client, URI base,
                     String path, String contentType,
                     HttpRequest.BodyPublisher body, String label)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(
                    base.resolve(path))
                .header("Content-Type", contentType)
                .POST(body)
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        System.out.println(label + ": " + response.statusCode()
                + " " + response.body());
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("body-demo-", ".txt");

        try {
            Files.writeString(
                    file, "file-body", StandardCharsets.UTF_8);

            HttpServer server = HttpServer.create(
                    new InetSocketAddress(
                            InetAddress.getByName("127.0.0.1"), 0), 0);
            server.createContext("/", BodyPublisherDemo::handle);
            server.start();

            try {
                URI base = URI.create(
                        "http://127.0.0.1:"
                        + server.getAddress().getPort() + "/");
                HttpClient client = HttpClient.newHttpClient();

                // Unicode escape produces the exact 'à' character across all shells.
                HttpRequest.BodyPublisher text =
                        HttpRequest.BodyPublishers.ofString(
                                "Xin ch\u00e0o", StandardCharsets.UTF_8);

                byte[] raw = {0x00, 0x01, (byte) 0xFF, 0x7F};
                HttpRequest.BodyPublisher bytes =
                        HttpRequest.BodyPublishers.ofByteArray(raw);

                HttpRequest.BodyPublisher fromFile =
                        HttpRequest.BodyPublishers.ofFile(file);

                byte[] streamBytes = "stream-body".getBytes(
                        StandardCharsets.UTF_8);
                Supplier<InputStream> supplier =
                        () -> new ByteArrayInputStream(streamBytes);
                HttpRequest.BodyPublisher stream =
                        HttpRequest.BodyPublishers.ofInputStream(supplier);

                System.out.println(
                        "Lengths: " + text.contentLength()
                        + ", " + bytes.contentLength()
                        + ", " + fromFile.contentLength()
                        + ", " + stream.contentLength());

                post(client, base, "string",
                        "text/plain; charset=utf-8", text, "String");
                post(client, base, "bytes",
                        "application/octet-stream", bytes, "byte[]");
                post(client, base, "file",
                        "text/plain; charset=utf-8", fromFile, "File");
                post(client, base, "stream",
                        "application/octet-stream", stream, "InputStream");
            } finally {
                server.stop(0);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile/run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 BodyPublisherDemo.java
java BodyPublisherDemo
~~~

Stdout verified on JDK 17 with the `jdk.httpserver` module available:

~~~text
Lengths: 9, 4, 9, -1
String: 200 POST /string bytes=9 type=text/plain; charset=utf-8
byte[]: 200 POST /bytes bytes=4 type=application/octet-stream
File: 200 POST /file bytes=9 type=text/plain; charset=utf-8
InputStream: 200 POST /stream bytes=11 type=application/octet-stream
~~~

### 9.1. Explaining Stdout

- **`Lengths: 9, 4, 9, -1`** are respectively the `contentLength()` of `ofString`, `ofByteArray`, `ofFile`, and `ofInputStream`. `-1` means **unknown length**, not an HTTP error or an empty body.
- **String 9 bytes:** `"Xin ch\u00e0o"` produces the Vietnamese text “Xin chào”; UTF-8 uses 9 bytes, even though Java `String.length()` is 8.
- **byte[] 4 bytes:** includes both `0x00` and `0xFF` — the server counts all 4 bytes accurately without interpreting them as text.
- **File 9 bytes:** the temporary file containing `file-body` is streamed as the request body; the file is deleted after all requests finish.
- **InputStream 11 bytes:** the supplier returns a new `ByteArrayInputStream` over the array containing `stream-body`. The publisher does not declare the size in advance, yet the server **still receives all 11 bytes**.
- All four requests are sent via `POST` and all receive `200` from the **demo server**. A real server may return `201`, `204`, or `4xx/5xx` depending on its contract; the client must check `statusCode()`.

### 9.2. Why Doesn't the Server Print `Transfer-Encoding`?

The goal of the demo is to **compare actual bytes received and BodyPublisher types**, not to lock into a single HTTP version/wire framing. `HttpClient` may choose HTTP/1.1 or HTTP/2 depending on the peer; the `jdk.httpserver` server in the demo speaks HTTP/1.1, but the app should not rely on a framing header to conclude that BodyPublisher works.

On the server side, reading the request body from `exchange.getRequestBody()` returns **the body bytes after the HTTP parser has handled framing**. Therefore all 11 bytes of the `InputStream` are still received properly even though the publisher reports length `-1`.

### 9.3. Why Use a Temporary File in the Demo?

So the program can run repeatedly without depending on an existing file, it creates a file with `Files.createTempFile`, writes known content, and sends it with `ofFile`. `finally` ensures the server stops and deletes the temporary file even if a request fails, **after `send` has finished or thrown**. When using `sendAsync`, you must clean up the file **after the CompletionStage actually completes**, not immediately when creating the future.

### 9.4. Production Safety

The demo server uses `readAllBytes` to illustrate very small payloads. Do not copy this pattern verbatim to an arbitrary file-upload endpoint without byte limits; an attacker could send an unknown-length or oversized body and exhaust the heap. Production requires enforcing max byte limits, read timeouts, content-type validation, authentication, quotas, storage, and cleanup.

## 10. Handling Large File Uploads Without High RAM Usage

Two approaches:

~~~java
// Approach A: Load the entire file into memory. Bad for very large files.
byte[] all = Files.readAllBytes(path);
HttpRequest.BodyPublisher fromMemory =
        HttpRequest.BodyPublishers.ofByteArray(all);

// Approach B: Publisher reads the file contents directly.
HttpRequest.BodyPublisher fromDisk =
        HttpRequest.BodyPublishers.ofFile(path);
~~~

This is illustrative code with a valid `path`. For a 2 GiB file, approach A may not be feasible on the heap, whereas approach B does not require allocating a 2 GiB byte array up front. **There is no guarantee that RAM stays strictly constant and tiny**: HttpClient/providers still have internal buffers, TLS, OS buffering, and request concurrency.

### 10.1. Resource Allocation Across Concurrent Streams

If running 100 concurrent uploads, you must account for:

- File/stream size and disk read throughput.
- HTTP client connection pool, TLS, CPU, outbound network bandwidth.
- Number of open file descriptors/InputStreams simultaneously.
- Timeouts and the possibility of a slow-reading server.
- Outbound bandwidth, retries, and buffer/backpressure load.
- Endpoint quotas, concurrent request limits, and whether the application supports canceling uploads.

`ofFile`/`ofInputStream` helps avoid a huge copy on the heap, but **does not automatically solve concurrency limits, safe retries, or timeouts**. Use `Semaphore`, executors, and workload-appropriate metrics if you have thousands of upload tasks.

### 10.2. No Need to Manually Chunk a File Just Because It Is Large

A file can be sent by the publisher/client across many network writes/frames. HTTP/TCP fragments data at the appropriate layer. Manually splitting a file into multiple HTTP requests is only needed when **the server supports resumable/chunked uploads at the application protocol level** or you need per-part retry management.

`Transfer-Encoding: chunked` in HTTP/1.1 is **wire framing**, not splitting an upload into multiple requests. Likewise, HTTP/2 DATA frames are not application-level data chunks you can reassemble arbitrarily if the server expects multipart or a single unified hash.

## 11. Streaming InputStream: Common Lifecycle Pitfalls

### 11.1. Wrong: Reusing an Already-Opened InputStream

~~~java
InputStream once = Files.newInputStream(path);
HttpRequest.BodyPublisher wrong =
        HttpRequest.BodyPublishers.ofInputStream(() -> once);
~~~

This is **an example of wrong code**. The supplier returns the same stream on every call; after the first subscription, the stream is at EOF or closed. If HttpClient needs to publish again, the body may be missing or fail. The right way is for the supplier to **open a new stream each time** (when the source is replayable).

### 11.2. Wrong: Closing a File/Stream Too Early

~~~java
// WRONG before the request has been sent:
Path temp = createTempFileSomehow();
HttpRequest request = HttpRequest.newBuilder(uri)
        .POST(HttpRequest.BodyPublishers.ofFile(temp))
        .build();
Files.delete(temp); // The file may be gone before the body is read!
client.send(request, HttpResponse.BodyHandlers.discarding());
~~~

The snippet above uses a hypothetical function name `createTempFileSomehow` and application variables; it is **not a standalone runnable example**. It illustrates a lifecycle bug: building a request does not mean the file has already been loaded.

With `sendAsync`:

~~~java
CompletableFuture<HttpResponse<Void>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding());

// Do not delete temp here.
// Clean up when the future completes and the result/error has been handled.
future.whenComplete((response, error) -> {
    try {
        Files.deleteIfExists(temp);
    } catch (IOException closeError) {
        // Log it; do not silently leak temp files.
    }
});
~~~

This is an **illustrative snippet with declared variables**, requiring imports for `java.util.concurrent.CompletableFuture`, `java.nio.file.Files`, and `java.io.IOException`. In real production code, you must also handle publisher resources, cancellation, security, and backpressure; `whenComplete` attaches cleanup when the future finishes and does not replace a retry policy.

### 11.3. Wrong: Supplier Throwing Checked IOException Directly

~~~java
// WRONG: Supplier.get() lambda cannot throw checked IOException.
Supplier<InputStream> bad =
        () -> Files.newInputStream(path);
~~~

The fix:

~~~java
Supplier<InputStream> good = () -> {
    try {
        return Files.newInputStream(path);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};
~~~

This is illustrative code; it requires importing `java.io.*`, `java.nio.file.*`, and `java.util.function.Supplier`. If the file cannot be opened, the request **must fail**, not fall back to an empty stream to pretend the upload succeeded.

### 11.4. One-Shot Read-Only Sources

A camera stream, process stdout, or incoming socket may **not be recreatable from the first byte**. `ofInputStream` can still consume a stream in a single send, but it cannot guarantee the body can be replayed if a retry, redirect, or authentication requires re-subscribing.

If correctness requires retries, choose one of: save a snapshot to a file first; store the body as ID-tagged chunks and recover per protocol; or fail and ask the user to regenerate the data. Do not silently send “the remaining part” as the full body after the old HTTP connection fails.

## 12. File Upload Does Not Mean multipart/form-data

### 12.1. Raw Body

If the server defines:

~~~http
POST /upload/raw HTTP/1.1
Content-Type: application/octet-stream

<raw file bytes>
~~~

then `ofFile(path)` fits well. The body is **the file's bytes**, with no form fields or automatic filename. The server may receive the filename via URL or a custom-designed metadata header.

### 12.2. Multipart Form Body

A common form upload expects:

~~~http
POST /upload/form HTTP/1.1
Content-Type: multipart/form-data; boundary=Boundary123

--Boundary123
Content-Disposition: form-data; name="file"; filename="demo.txt"
Content-Type: text/plain

<file bytes>
--Boundary123--
~~~

In the actual wire format, multipart uses **CRLF** (carriage return + line feed) with exact syntax, and the boundary must be valid/safe. `ofFile(path)` **does not automatically generate** `Content-Disposition` lines, boundaries, or form parts. Only changing the header to `multipart/form-data` without framing the body is a common mistake.

In Java 17, you can build multipart by concatenating publishers (`BodyPublishers.concat(...)`) with proper headers/CRLF, but manually handling filename quoting, charsets, boundary collisions, and safe sizing/streaming is very error-prone. For real systems, prefer a battle-tested multipart builder/framework, or follow the raw-body endpoint contract if the server supports it.

### 12.3. Using JSON for Binary Files?

Base64-encoding a file and embedding it in JSON is a **different** contract from raw upload or multipart. Base64 increases payload size and requires encoding/decoding; only use it when the server API explicitly defines that format. `ofByteArray` and `ofFile` do not automatically Base64-encode contents.

## 13. `send`, `sendAsync`, Retries, and Timeouts

### 13.1. Synchronous Send

~~~java
HttpResponse<String> response =
        client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    // Success in the HTTP 2xx status class;
    // still need to check the specific API contract.
} else {
    // Handle status and response body/error.
}
~~~

The illustrative snippet requires `client`/`request` variables and checked exceptions. `send` waits for the response per the API; the upload happens while the request is transmitted. **Status 200 only means the server returned OK**, it does not guarantee business processing succeeded or the file was persisted permanently; the API may use 201/202/204.

### 13.2. Asynchronous Send

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

future.thenAccept(response -> {
    System.out.println("HTTP " + response.statusCode());
}).exceptionally(error -> {
    // Log and handle upload failure.
    return null;
});
~~~

This is illustrative code; it requires importing `CompletableFuture`. `sendAsync` returns a Future/CompletionStage early, which **does not mean the file/stream body has finished being read** when it returns. You must manage the file source and lifecycle according to actual completion; callbacks/CompletionStages may run on a different thread.

### 13.3. Timeouts

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(30))
        .POST(publisher)
        .build();
~~~

The illustrative code requires importing `java.time.Duration` and the HTTP types. `connectTimeout` applies to the connection phase; `request.timeout` is the duration threshold for the request per `HttpClient` semantics. Do not treat them as the sole defense against a hanging InputStream source or a server that stops reading: test cancellation, timeouts, and actual resource behavior.

### 13.4. Retries Can Duplicate Side Effects

If the client sends 90% of the body, the connection drops, and no response is received, **you cannot know for sure whether the server finished processing it**. Even when using `ofFile` or a reopenable supplier, retrying a `POST` can duplicate its effect. Only retry when the endpoint allows it or when using a request ID/idempotency key. Do not infer “replayable BodyPublisher = HTTP request is safe to auto-retry”.

For very large uploads, consider a server-defined **resumable upload** protocol, which typically includes an upload session ID, offset, checksum, and reconciliation. Trying to resume mid-way on an old TCP stream after a failure is not a valid upload resume mechanism.

## 14. Failure Modes and How to Handle Them

| Error | Symptom | How to handle |
| --- | --- | --- |
| Sending JSON with ofString without setting Content-Type | Server does not know the right media type | Set `application/json; charset=utf-8` |
| Using default charset unintentionally | Server decodes text incorrectly | Use `StandardCharsets.UTF_8` and consistent metadata |
| Using `String.length()` as byte count | Byte count wrong for Vietnamese/emoji | Measure bytes after encoding or let the publisher compute it |
| Using ofByteArray for huge files via readAllBytes | OOM/heap pressure | Use `ofFile` or a streaming InputStream |
| Calling ofFile for a nonexistent/unreadable file | Request cannot publish body | Handle `FileNotFoundException`/I/O, validate path |
| Deleting file after build but before send | File is gone when client tries to read it | Wait for send/sendAsync completion before cleanup |
| File overwritten/truncated during upload | Wrong content/length, request fails | Create a snapshot or lock lifecycle logic |
| Using ofFile when server expects multipart | Server reports missing boundary/form field | Use a proper multipart encoder, not just Content-Type |
| Supplier returns the same old InputStream | Retry/later subscription hits EOF | Open a fresh stream each time the supplier is called |
| Supplier throws checked IOException directly | Code does not compile | Catch and wrap in `UncheckedIOException` |
| Interpreting `contentLength()==-1` as no body | Wrong body length reported | `-1` means unknown length |
| Manually setting mismatched Content-Length | Broken request framing/rejected by HTTP client | Let HttpClient manage it |
| Assuming ofInputStream encodes text automatically | Byte stream has no charset magic | Encode beforehand or define the data format |
| Treating HTTP 4xx/5xx as having no response body | Missing error details | Read response and handle status explicitly |
| Calling sendAsync then deleting file immediately | File disappears while upload is reading | Clean up via completion callback |
| Retrying POST without an idempotency key | May create duplicate transactions | Follow API contract, idempotency / reconciliation |
| Using HTTPS without server verification | Risk of sending sensitive data to wrong peer | Keep trust/identity validation enabled, do not bypass TLS |
| Demo server reads unbounded uploads with readAllBytes | Runs out of RAM on large uploads | Limit body size, use streaming parser, quotas |

## 15. Practical Scenarios

### Scenario A — Sending JSON to Create a User

You already have a JSON String produced by a serializer. The `POST /users` endpoint expects UTF-8 JSON and the payload is small. Which publisher makes sense?

**Answer:** `ofString(json, StandardCharsets.UTF_8)` and `Content-Type: application/json; charset=utf-8`. The client parses the response with a separate BodyHandler. No need to manually convert JSON to `byte[]` unless you already have the bytes.

### Scenario B — Sending Pre-Serialized Protobuf Bytes

You have `byte[] protobufBytes`, and the endpoint accepts `application/x-protobuf` and requires exact bytes.

**Answer:** `ofByteArray(protobufBytes)` with the proper media type; do not call `new String(bytes)`. If sending only a segment, use the `ofByteArray(array, offset, length)` overload.

### Scenario C — Uploading a 500 MiB File

You have a `Path` to a validated file and the server accepts a raw body. Should you call `Files.readAllBytes` and then `ofByteArray`?

**Answer:** usually no. `ofFile(path)` reduces the need to hold the entire file in RAM; keep the file stable throughout the upload, set timeouts/limits, and verify the server contract. Do not assume the file will be sent as multipart.

### Scenario D — Stream Generating Data on Demand

A filter produces data as it is read and only exposes an `InputStream`. The total size is unknown in advance.

**Answer:** `ofInputStream(() -> freshStream())` if the source can supply a new stream on demand. `contentLength()==-1`; the HTTP client chooses the framing. If only a single stream can be created, you must clearly define retry/redirect policy, cancellation, and failure conditions.

### Scenario E — Encountering a 307/308 Redirect During Upload

An endpoint returns a redirect where the method/body may need to be resent to the new URL. The supplier is returning the same exhausted InputStream.

**Answer:** it may fail or send an invalid body when the request is replayed. The supplier needs a **fresh stream**, and you must **not** blindly allow redirecting sensitive uploads to arbitrary origins. Check `HttpClient.Redirect`, auth/headers, scheme, host allowlist, and idempotency.

### Scenario F — Temporary File Created for an Async Upload

Code builds `ofFile(temp)`, calls `sendAsync`, then calls `Files.delete(temp)` on the very next line.

**Answer:** wrong lifecycle. When `sendAsync` returns, the upload may not have started or finished yet. Only delete the file after the future actually completes and errors have been handled.

### Scenario G — Server Requires Fixed Content-Length

An older proxy/endpoint rejects request bodies with unknown length. You are using `ofInputStream`.

**Answer:** change strategy per the contract: write to a temp file and use `ofFile`, or load into a byte[] if small and bounded, or use a publisher capable of declaring the exact length when guaranteed. Do not just manually set a Content-Length that conflicts with `contentLength()==-1`.

### Scenario H — Unicode and Content-Type

The client sends `"Xin chào"` but declares `text/plain; charset=us-ascii`. What is the problem?

**Answer:** the UTF-8 bytes contain a multi-byte sequence for `à`, whereas the header advertises US-ASCII. The server may decode it incorrectly or reject it. Use a charset that matches the encoding, and test the actual bytes sent.

### Scenario I — API Returns 201 Created

The client uploads with `ofFile`; the response returns `201 Created` and a `Location` header instead of `200`. Did the upload fail?

**Answer:** no. 201 is an HTTP success code for a created resource; check the API contract, Location, and response body; do not hardcode that only status 200 counts as success.

### Scenario J — Encryption and Security

The file contains sensitive data, and the request uses plain HTTP over the Internet. Does BodyPublisher encrypt it automatically?

**Answer:** no. BodyPublisher selects **the source of request body bytes**; it does not create TLS. Use HTTPS and verify server certificates/hostnames, authz, URL/redirect scope, logging, and file source controls. Do not send secrets to a user-controlled host just because “there is SSL elsewhere”.

## 16. HTTP Request Body Programming Checklist

- [ ] Know whether the body is actually text, binary bytes, a raw file, or a reopenable stream?
- [ ] Using the right `ofString` / `ofByteArray` / `ofFile` / `ofInputStream`?
- [ ] For String, encoding with UTF-8 and declaring a consistent charset/media type?
- [ ] For bytes, avoiding arbitrarily converting binary data into a String?
- [ ] For large files, avoiding `readAllBytes` into the heap when unnecessary?
- [ ] Distinguished raw file upload from `multipart/form-data` with boundary/filename?
- [ ] InputStream supplier creates a **fresh** stream each time it is called, not returning an old/closed stream?
- [ ] When the stream source is non-replayable, have a clear retry/redirect/timeout policy?
- [ ] Checked `contentLength()` = byte size or -1 (unknown)?
- [ ] Not manually setting `Content-Length`/`Transfer-Encoding` in conflict with HttpClient?
- [ ] HTTP method and `Content-Type` match the endpoint's contract?
- [ ] Distinguished BodyPublisher (sending) from BodyHandler (receiving)?
- [ ] Not deleting/mutating the file or byte source before send/sendAsync finishes?
- [ ] Checked response status 2xx/4xx/5xx, parsed errors, and closed resources properly?
- [ ] Enforced limits on payload size, concurrent uploads, timeouts, bandwidth, and quotas?
- [ ] Configured appropriate HTTPS/trust/auth when sending sensitive data, and a safe redirect policy?
- [ ] For operations with side effects, retries use an idempotency key or reconciliation?
- [ ] Tested non-ASCII strings, `0x00` bytes, empty/large files, unknown-length streams, server rejections, and upload cancellation?

**Conclusion:** `HttpRequest.BodyPublishers` turns **application data sources** into request bodies for Java `HttpClient`. `ofString` suits text with a charset, `ofByteArray` suits existing bytes, `ofFile` suits reading files directly without loading them completely into RAM, and `ofInputStream` suits streaming data with a **supplier that creates a stream when needed**. To send HTTP correctly, you must still combine this with **Content-Type, actual byte counts, HTTP method, source lifecycle, retry/idempotency, timeouts, and the server contract** — BodyPublisher does not solve all of those on its own.

## 17. Official API Documentation

- **Java 17 — HttpRequest.BodyPublishers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- **Java 17 — HttpRequest.BodyPublisher:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html
- **Java 17 — HttpRequest:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 — HttpResponse.BodyHandlers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- **Java 17 — HttpServer (local demo):** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html

The APIs here are for Java 17+ per the lesson's target. When running on a different JDK/provider or with HTTP/2, proxies, redirects, authentication, and slow stream sources, verify actual responses, retry policies, and API contracts rather than extrapolating from a single simple upload.