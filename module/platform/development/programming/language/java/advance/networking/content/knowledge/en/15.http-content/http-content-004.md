# Receiving HTTP Content with ofString, ofByteArray, ofFile, and discarding in Java

When Java sends an `HttpRequest` using the `java.net.http` module, **how the response body is handled is determined by the `HttpResponse.BodyHandler<T>`** that the application passes to `HttpClient.send(...)` or `sendAsync(...)`. The four most common choices are:

- **`BodyHandlers.ofString(...)`**: decodes the response body into a **`String`** (text data).
- **`BodyHandlers.ofByteArray()`**: collects the response body into a **`byte[]`** (preserving raw bytes).
- **`BodyHandlers.ofFile(path, ...)`**: writes the response body to a **file**, returning a **`Path`**.
- **`BodyHandlers.discarding()`**: **reads and discards** the body, returning a body of type **`Void`** (actual value `null`).

Choosing the wrong handler can cause the application to decode with the wrong charset, use too much RAM, overwrite files unintentionally, or waste effort processing an unnecessary body. **HTTP status, headers, and body data type are three separate concerns**: HTTP 404 can still be handled by all four handlers; they **do not automatically reject** a response just because the status is an error.

This lesson is part of the **HTTP Content** topic of Java Advance - networking, focusing on how to receive content and resource lifecycle. There are two **complete Java 17+ programs that run on localhost without requiring Internet**, accompanied by `javac`/`java` commands, deterministic output, and explanations of limitations.

## 1. Where BodyHandler Fits in the HTTP Flow

In the Java HTTP Client:

~~~text
Application                      HTTP server
    |                                  |
    | HttpRequest                      |
    | URI / method / headers / body    |
    +---------- request -------------> |
    |                                  |
    | <--- status + headers + bytes ---+
    |
    v
HttpClient.send(request, BodyHandler<T>)
    |
    +-- ofString(UTF_8)  --> HttpResponse<String>
    |
    +-- ofByteArray()    --> HttpResponse<byte[]>
    |
    +-- ofFile(path)     --> HttpResponse<Path>
    |
    +-- discarding()     --> HttpResponse<Void>
    |
    +-- all have statusCode(), headers(), version(), uri()
~~~

`HttpClient` handles sending the HTTP request and receiving the response; **`BodyHandler<T>` chooses how to accept the body**. Predefined handlers typically create the corresponding `BodySubscriber<T>`. The subscriber processes the byte stream from the transport and completes the result of type `T`.

Simple recipe:

~~~java
HttpResponse<String> text = client.send(
        request, HttpResponse.BodyHandlers.ofString());

HttpResponse<byte[]> binary = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<Path> saved = client.send(
        request, HttpResponse.BodyHandlers.ofFile(outputPath));

HttpResponse<Void> ignored = client.send(
        request, HttpResponse.BodyHandlers.discarding());
~~~

**This is a snippet**, not a complete program. It requires `client`, `request`, `outputPath`, imports, and exception handling. The four statements above will **send four separate HTTP requests**, not receive one response and switch handlers. Do not test sequentially like this with a POST that creates data if you do not want to perform the action four times.

**Distinction from `BodyPublisher`:**
- `HttpRequest.BodyPublisher` emits **outgoing request** data (for example, `BodyPublishers.ofString(json)` in POST).
- `HttpResponse.BodyHandler` processes **incoming response** data.
- `HttpResponse<T>` is the metadata + body result produced by that handler.

## 2. Quick Comparison Table of the Four Choices

| Handler | Type `T` in `HttpResponse<T>` | Returned body | When appropriate | Main cost/risk |
| --- | --- | --- | --- | --- |
| `ofString(charset)` | `String` | Decoded text | Small JSON/text, HTML, moderate API error body | Holds entire body in RAM; can use wrong charset |
| `ofByteArray()` | `byte[]` | Raw bytes | Small images/binaries, checksums, data needing a custom parser | Holds all bytes in RAM |
| `ofFile(path, options...)` | `Path` | Path to the written file | Downloading large content, files that need to be saved | Write permissions, disk full, corrupt/partial file, overwriting |
| `discarding()` | `Void` | `null` | Only care about status/headers, do not need body | Still incurs processing/network cost to consume body, no data for debugging |

A few guidelines:
1. **Text and charset known in advance**: `ofString(StandardCharsets.UTF_8)`.
2. **Want to preserve exact bytes**: `ofByteArray()`, then parse/decode explicitly.
3. **Need to save a file instead of keeping everything on the heap**: `ofFile(path, options)`, check disk/size/status.
4. **Only need to know the response arrived and its status**: `discarding()`.
5. **Very large body where writing to a file is not allowed**: you can consider `ofInputStream()` or the Flow API; these are different APIs and require explicitly closing the stream/designing backpressure.

There is no single "best" handler for every API. The same endpoint returning video, JSON, and text errors may need different body policies depending on status/Content-Type.

## 3. ofString(): Decoding into String

Syntax:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

String body = response.body();
int status = response.statusCode();
~~~

This is a **snippet**, requiring imports `java.net.http.*` and `java.nio.charset.StandardCharsets`. Use it when the response is expected to be text and not large, such as JSON APIs, XML, text messages, or small HTML.

`BodyHandlers.ofString(Charset)` **uses the exact charset you provide**. With UTF-8:

~~~java
BodyHandlers.ofString(StandardCharsets.UTF_8)
~~~

means converting UTF-8 bytes into Java characters. If the server sends bytes in a different charset, UTF-8 decoding can produce replacement characters (``) or garbled text without necessarily throwing an exception.

### How is the no-argument ofString() different?

According to the Java 17 Javadoc, `BodyHandlers.ofString()` **looks up the charset from the `Content-Type` header** of the response. If the header has no charset or the charset is not supported, it **falls back to UTF-8**.

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=ISO-8859-1

...
~~~

With `ofString()`, the handler can select ISO-8859-1 from the header. With `ofString(StandardCharsets.UTF_8)`, the application has **fixed UTF-8**; this is a useful choice when the API contract explicitly states the response is always UTF-8, though it will not automatically follow a different charset in the header.

Notes:
- `Content-Type` is a **header declared by the server**; the server can declare it incorrectly. Verify the API contract if the data is important.
- `Content-Encoding: gzip` is a **content coding**, not a character encoding. Changing the charset does not automatically "decompress" gzip. Do not assume handlers resolve all compression variants; check client configuration/headers and implement necessary decoding.
- `String.length()` counts UTF-16 code units, not bytes on the wire. A UTF-8 Vietnamese character can occupy multiple bytes but only one UTF-16 code unit.
- `ofString` typically keeps the entire response body in memory before `send` returns the text result. It is unsuitable for data that may be unbounded or too large.
- For JSON, `ofString` only **decodes bytes into text**; it does not automatically parse JSON into a Java object.

**Use when:** small REST responses, text configs, short API results, error bodies that you want to display/log in a controlled manner.

## 4. ofByteArray(): Receiving Raw Bytes

Syntax:

~~~java
HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

byte[] bytes = response.body();
System.out.println("Received bytes: " + bytes.length);
~~~

This is a snippet. `ofByteArray()` **does not interpret a charset and does not alter content according to text encoding**; you receive the body bytes in the representation that the HTTP client delivers to the handler. To decode text, you decide the charset afterward:

~~~java
String text = new String(response.body(), StandardCharsets.UTF_8);
~~~

Only do this when you actually know the bytes are UTF-8. If the body is PNG, ZIP, PDF, or binary-encoded data, using `new String(...)` will lose the binary meaning.

### Bytes in Java are signed

Java `byte` has a range of -128..127. For example, if the body has a byte with unsigned value `0xFF`, it will appear as `-1` when viewed via `Arrays.toString(byteArray)`. That is **not** data corruption caused by HTTP.

Convert a byte to an unsigned number:

~~~java
int unsigned = bytes[index] & 0xff;
~~~

Or print hex bytes on Java 17+:

~~~java
String hex = HexFormat.of().formatHex(bytes);
~~~

Requires `import java.util.HexFormat;`. For example, the bytes `00 01 02 FF` print as `000102ff`.

### Be careful with RAM

`ofByteArray()` must hold the bytes needed for the result array in memory. Large responses can cause memory pressure/OOM, especially when many requests run concurrently. If the goal is just to save a file, `ofFile()` is more appropriate. If streaming parsing is needed, `BodyHandlers.ofInputStream()` or a custom subscriber allows a different approach — but that means you take responsibility for lifecycle/limits.

**Use when:** small images/files, binary protocols, checksums, bytes to feed to a parser, signature verification, or content whose encoding has not yet been determined.

## 5. ofFile(): Writing the Body to a File and Returning Path

Syntax:

~~~java
Path output = Path.of("download.bin");

HttpResponse<Path> response = client.send(
        request, HttpResponse.BodyHandlers.ofFile(
                output,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE));

Path saved = response.body();
long size = Files.size(saved);
~~~

This is a snippet: requires imports `java.nio.file.*`, `java.net.http.*`. **`CREATE_NEW` requires the destination file not to exist yet** and causes the operation to fail if the file already exists. Use this mode to avoid unwanted overwrites.

According to the Javadoc, with `BodyHandlers.ofFile(...)`, when `HttpResponse<Path>` returns, **the body has finished being written to the file** if the operation succeeded. `response.body()` is a `Path`, **not** bytes or String content.

**Path examples:**
- `Path.of("download.bin")` is a relative path, resolved against the JVM's working directory.
- `Path.of("/data/download.bin")` is a Unix-style absolute path; Windows has a different path syntax.
- `Files.createTempDirectory(...)` and `directory.resolve("payload.bin")` create a controlled temporary destination, suitable for tests.

**Do not use `ofFile` to blindly trust a filename from the server.** In this API, the path is **chosen by you in advance**; unlike `BodyHandlers.ofFileDownload(directory, options...)` which takes the name from `Content-Disposition`. If using a filename from an external source, you must normalize, restrict to the directory, check for path traversal, and avoid overwriting.

### Important trap: ofFile(path) does not truncate an existing file by default

The Java 17 Javadoc explicitly states:

~~~java
BodyHandlers.ofFile(path)
~~~

is equivalent to:

~~~java
BodyHandlers.ofFile(
        path, StandardOpenOption.CREATE, StandardOpenOption.WRITE)
~~~

**There is no `TRUNCATE_EXISTING` in the default.** When writing a shorter response over an **existing longer file**, old data **may still remain at the end of the file**. This is very easy to confuse with `Files.writeString(path, text)` — the two APIs have different default open options.

Choose intentionally:

| Goal | Open options | Meaning |
| --- | --- | --- |
| Create a new file, must not collide | `CREATE_NEW, WRITE` | Prevents overwrite; fails if it already exists |
| Allow replacing existing file content | `CREATE, WRITE, TRUNCATE_EXISTING` | Truncates the file before writing |
| Use default `ofFile(path)` | `CREATE, WRITE` | Can leave trailing bytes from an older, longer file |
| Download to temp then publish after verification | Temp file + verify + move | Reduces risk of promoting a corrupt/partial file to production |

These options are `java.nio.file.StandardOpenOption` and must be valid per the Javadoc. Do not arbitrarily combine `APPEND` with `TRUNCATE_EXISTING`.

### Error files or HTTP error bodies

`BodyHandlers.ofFile(...)` **does not automatically discard the body of a 404/500 response**. For example, if the server returns 404 with an HTML error page, the handler can still write that HTML into `download.bin` and return `HttpResponse<Path>` with `statusCode()==404`.

Therefore:
1. Check `statusCode()` after receiving the response.
2. Check `Content-Type`, size, checksum/signature (if available) according to business rules.
3. If invalid, **delete/quarantine** the temporary file; do not serve it to users as a valid file.
4. If the download is accepted, move the temporary file to the final destination with an appropriate anti-overwrite policy.

If the network drops, the filesystem fills up, or write permission is denied, `send()/sendAsync()` can fail. A file that **was created but partially written** may still exist; cleanup is needed in the error branch. I/O errors do not always cause the API to delete the file automatically.

**Use when:** downloading reports, saving images or large files, saving backups/exports, or needing a `Path` result without holding everything in a Java `byte[]`.

## 6. discarding(): Discarding Content While Still Getting Metadata

Syntax:

~~~java
HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());

System.out.println(response.statusCode());
System.out.println(response.headers().firstValue("Content-Type"));
System.out.println(response.body() == null);
~~~

This is a snippet, and the body will be `null` for `Void`. **Do not confuse `body()==null` with the server returning HTTP 204 No Content**: even if the server returns HTTP 200/202 with a body, discarding still drops that body.

`discarding()` is useful if:
- You only need the endpoint's status code after calling the request.
- You do not need to read the error payload.
- You need to inspect response headers and do not care about the body.
- You want to avoid holding a large body in RAM.

However, it **does not** make the HTTP request "free": the transport still has to process/deliver data according to the HTTP flow to complete the response. Discarding also **does not replace GET with HEAD**; the server may have already generated the body and transmitted the data. When you only want headers and the server supports it, use HTTP `HEAD`:

~~~java
HttpRequest head = HttpRequest.newBuilder(uri)
        .method("HEAD", HttpRequest.BodyPublishers.noBody())
        .build();
~~~

This is a snippet with a `uri` variable. Although HEAD typically has no message body, a server may be configured differently; you should not use HEAD for an endpoint that only supports GET/POST without checking the contract.

**Note:** `discarding()` can cause you to lose error information from the response body, such as JSON error details. If you need debugging or meaningful error messages, choose a handler that reads a bounded body on appropriate requests.

## 7. Predefined Handlers Do Not Automatically Check HTTP Status

The `HttpResponse.BodyHandlers` Javadoc explicitly states that predefined handlers **do not inspect the status code**: they accept the body regardless of status. For a valid HTTP response:

| HTTP response | ofString | ofByteArray | ofFile | discarding |
| --- | --- | --- | --- | --- |
| 200 + text | Text | Bytes | Writes text bytes to file | Body=null |
| 200 + binary | May decode into garbled characters | Exact bytes | Writes bytes to file | Body=null |
| 404 + HTML error body | HTML error String | HTML bytes | May write error page to file | Body=null |
| 500 + JSON error body | JSON text | JSON bytes | May write JSON to file | Body=null |
| 204 No Content | Empty String (per handler semantics) | Empty array | 0-byte file or no data to write, depending on path config | Body=null |

**Do not** equate `HTTP 404` with `IOException`. An HTTP 404 is a normal protocol-level response, whereas `IOException` typically indicates DNS, connection, TLS, or I/O processing errors. Check status separately:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

if (response.statusCode() >= 200 && response.statusCode() < 300) {
    // Handle body in the success case.
} else {
    // Handle error response, optionally log error body safely.
}
~~~

This is a snippet. Do not assume all 3xx codes are errors: the client's redirect policy may not follow or may follow according to configuration. Do not assume all 2xx codes have a non-empty body, as 204 is a successful response with no content.

An application wanting to **choose a handler by status** can create a custom `HttpResponse.BodyHandler<T>` based on `HttpResponse.ResponseInfo.statusCode()` to pick an appropriate `BodySubscriber<T>` (must agree on the same type `T`). For simple cases, using `ofString()` for bounded errors or downloading to a temp file and then checking status may be easier to maintain.

## 8. Complete Java 17+ Example: All Four Handlers in One Program

The **`FourResponseHandlersDemo.java`** program spins up a local HTTP server using `jdk.httpserver`:
- `/text` → HTTP 200, body `"hello"`.
- `/bytes` → HTTP 200, four bytes `00 01 02 FF`.
- `/file` → HTTP 200, body `"file=ready"`.
- `/ignore` → HTTP 202, body `"ignored-data"` (dropped by `discarding`).
- `/missing` → HTTP 404, body `"missing"` to demonstrate that an error response still has a body.

The server binds to `127.0.0.1:0`, using an OS-assigned port; no Internet, token, certificate, or DNS is required. The client selects HTTP/1.1 for the test environment. The file path is allocated in a separate temp directory, without touching application data.

Create the file **`FourResponseHandlersDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
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
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.HexFormat;

public class FourResponseHandlersDemo {
    static void reply(HttpExchange ex, int status,
                      byte[] data, String mime) throws IOException {
        ex.getResponseHeaders().set("Content-Type", mime);
        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static HttpRequest get(int port, String path) {
        return HttpRequest.newBuilder(URI.create(
                "http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(3)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("http-body-demo-");
        Path target = directory.resolve("payload.bin");

        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/", ex -> {
            try {
                String path = ex.getRequestURI().getPath();
                if (path.equals("/text")) {
                    reply(ex, 200,
                            "hello".getBytes(StandardCharsets.UTF_8),
                            "text/plain; charset=utf-8");
                } else if (path.equals("/bytes")) {
                    reply(ex, 200,
                            new byte[]{0, 1, 2, (byte) 255},
                            "application/octet-stream");
                } else if (path.equals("/file")) {
                    reply(ex, 200,
                            "file=ready".getBytes(StandardCharsets.UTF_8),
                            "application/octet-stream");
                } else if (path.equals("/ignore")) {
                    reply(ex, 202,
                            "ignored-data".getBytes(StandardCharsets.UTF_8),
                            "text/plain");
                } else {
                    reply(ex, 404,
                            "missing".getBytes(StandardCharsets.UTF_8),
                            "text/plain; charset=utf-8");
                }
            } catch (IOException error) {
                ex.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            // 1. Text => HttpResponse<String>.
            HttpResponse<String> text = client.send(
                    get(port, "/text"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("String: " + text.statusCode()
                    + " | " + text.body());

            // 2. Binary => HttpResponse<byte[]>.
            HttpResponse<byte[]> bytes = client.send(
                    get(port, "/bytes"),
                    HttpResponse.BodyHandlers.ofByteArray());
            System.out.println("Bytes: " + bytes.statusCode()
                    + " | " + HexFormat.of().formatHex(bytes.body()));

            // 3. File => HttpResponse<Path>.
            // CREATE_NEW prevents overwriting an existing file.
            HttpResponse<Path> file = client.send(
                    get(port, "/file"),
                    HttpResponse.BodyHandlers.ofFile(
                            target, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE));
            System.out.println("File: " + file.statusCode()
                    + " | " + Files.size(file.body()) + " bytes");
            System.out.println("File content: "
                    + Files.readString(
                            file.body(), StandardCharsets.UTF_8));

            // 4. Discard => HttpResponse<Void> and body() == null.
            HttpResponse<Void> ignored = client.send(
                    get(port, "/ignore"),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("Discard: " + ignored.statusCode()
                    + " | body == null: " + (ignored.body() == null));

            // 5. HTTP error can still be HttpResponse<String>.
            HttpResponse<String> error = client.send(
                    get(port, "/missing"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("Error: " + error.statusCode()
                    + " | " + error.body());
        } finally {
            server.stop(0);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 FourResponseHandlersDemo.java
java FourResponseHandlersDemo
~~~

**Verified output (independent of the chosen ephemeral port):**

~~~text
String: 200 | hello
Bytes: 200 | 000102ff
File: 200 | 10 bytes
File content: file=ready
Discard: 202 | body == null: true
Error: 404 | missing
~~~

### Why does it produce this output?

1. `BodyHandlers.ofString(UTF_8)` returns `HttpResponse<String>`, and the body is the string `"hello"`.
2. `BodyHandlers.ofByteArray()` preserves the four raw bytes; `HexFormat` prints `000102ff`, including the signed byte `(byte) 255`.
3. `BodyHandlers.ofFile(target, CREATE_NEW, WRITE)` writes 10 bytes `file=ready` into the new file; the response returns the `Path` to that same file.
4. `BodyHandlers.discarding()` drops `"ignored-data"` but the response still has HTTP status `202`. `body() == null` is normal for `HttpResponse<Void>`.
5. The `/missing` request returns HTTP 404 and text `"missing"`; `client.send(...)` does not throw an exception just because of status 404.
6. `Files.readString(file.body())` in the demo is only to inspect the **10-byte file**. In an application downloading large files, do not read the entire file back into a String, as that defeats the benefit of streaming-to-disk.
7. `finally` cleans up the server and temp files. If the program fails early, additional cleanup cases may arise depending on design; this is an illustrative fixture, not a user-facing download manager.

**Different modules:** The HTTP client classes belong to the **`java.net.http`** module; the test HTTP server `com.sun.net.httpserver.HttpServer` belongs to the **`jdk.httpserver`** module. In a Java project with an explicit `module-info.java`, you need `requires java.net.http;` and (only when using the test fixture) `requires jdk.httpserver;`. When running on the regular classpath with a full JDK, these examples can run without a module descriptor file.

## 9. Second Java 17+ Example: Existing File and TRUNCATE_EXISTING

This is an easily overlooked bug in report-downloading systems: the file `report.txt` currently has 26 bytes of content, and the new response only has 3 bytes. Calling `BodyHandlers.ofFile(path)` by default **does not truncate the old file**.

The following program compares:
1. Pre-writing the string `abcdefghijklmnopqrstuvwxyz` (26 ASCII bytes) to a temp file.
2. Using `ofFile(file)` to download the new body `abc` (3 bytes).
3. Checking the file length after the first run — still 26 bytes in the test environment.
4. Sending the same GET again but using `CREATE, WRITE, TRUNCATE_EXISTING` — the file length drops to the exact 3 bytes.

Create the file **`OfFileOpenOptionsDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
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
import java.nio.file.StandardOpenOption;

public class OfFileOpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/", exchange -> {
            byte[] content = "abc".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, content.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(content);
            }
        });

        Path file = Files.createTempFile(
                "http-file-options-", ".txt");
        server.start();
        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + server.getAddress().getPort() + "/"))
                    .GET().build();

            Files.writeString(
                    file, "abcdefghijklmnopqrstuvwxyz",
                    StandardCharsets.UTF_8);

            // Default is only CREATE + WRITE, no TRUNCATE.
            HttpResponse<Path> defaultSave = client.send(
                    request, HttpResponse.BodyHandlers.ofFile(file));

            System.out.println("Default length: "
                    + Files.size(defaultSave.body()));
            System.out.println("Default starts with abc: "
                    + Files.readString(file).startsWith("abc"));

            // Explicitly replace old content.
            HttpResponse<Path> truncatedSave = client.send(
                    request, HttpResponse.BodyHandlers.ofFile(
                            file, StandardOpenOption.CREATE,
                            StandardOpenOption.WRITE,
                            StandardOpenOption.TRUNCATE_EXISTING));

            System.out.println("Truncated length: "
                    + Files.size(truncatedSave.body()));
            System.out.println("Truncated content: "
                    + Files.readString(file));
        } finally {
            server.stop(0);
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 OfFileOpenOptionsDemo.java
java OfFileOpenOptionsDemo
~~~

**Test output on a JDK with a standard default filesystem provider:**

~~~text
Default length: 26
Default starts with abc: true
Truncated length: 3
Truncated content: abc
~~~

**Lesson from the demo:** A pre-existing filename is not enough to prove the downloaded body replaced it cleanly. `ofFile(file)` does not truncate by default. If you want to forbid overwriting, use `CREATE_NEW`. If you want to replace, use `TRUNCATE_EXISTING` intentionally. In production, a stronger approach is to write to a **separate temp file**, verify status/hash/size, and then move it to the destination using the Files API with an appropriate collision/atomicity policy.

## 10. Completion Mechanism and BodySubscriber

Handlers construct a `BodySubscriber<T>` to process the response byte stream. For the four simple choices:

~~~text
HTTP response headers ───> BodyHandler<T>
                                |
                                v
                         BodySubscriber<T>
                                |
                        ByteBuffer chunks
                                |
             +------------------+------------------+
             |                  |                  |
       accumulate text    accumulate bytes    write file/discard
             |                  |                  |
             v                  v                  v
          String              byte[]            Path / Void
                                |
                                v
                         HttpResponse<T>
~~~

For `ofString()`, `ofByteArray()`, `ofFile()`, and `discarding()`, a normal `send(...)` only returns once the handler has finished consuming the body according to its contract. Specifically, `ofFile()` has finished writing the body to the file when the response returns successfully. This is **different** from `BodyHandlers.ofInputStream()`, where the response can return after headers while the caller must continue reading/closing the `InputStream`.

**Do not equate "body finished writing to file" with "safe/valid content":** HTTP 404, wrong MIME, malware, checksum mismatch, or oversized content are still things the application must control.

With `sendAsync(...)`, the body is still processed by the same handler, only the way of receiving the result is a `CompletableFuture<HttpResponse<T>>`:

~~~java
CompletableFuture<HttpResponse<Path>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofFile(
                        path, StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE));

future.thenAccept(response -> {
    System.out.println(response.statusCode());
    System.out.println(response.body()); // Path.
});
~~~

This is a snippet; you must declare path, client, request, imports, and handle exceptional completion. Do not exit the JVM before the Future completes if the application needs the file. An `HttpResponse<T>` still carries the exact type `T` chosen in the BodyHandler.

## 11. Choosing a Handler Based on Needs and Content-Type

A practical strategy:

| What do you need to do? | Preferred handler | Additional checks |
| --- | --- | --- |
| Read small JSON to parse | `ofString(UTF_8)` or `ofByteArray()` | HTTP status, content-type, JSON schema, byte limit |
| Read text with known charset | `ofString(charset)` | Header/content contract and decoding errors |
| Receive small binary for in-memory processing | `ofByteArray()` | Size, MIME, magic bytes, checksum |
| Download large report/file | `ofFile(tempPath, options...)` | Status, filesize, checksum/signature, path/file permissions |
| Only need to know if HTTP call succeeded | `discarding()` | 2xx status, headers, trace ID, retry policy |
| Process huge data without saving a file | `ofInputStream()` or custom Flow subscriber | Stream limit, close/cancel, backpressure |

**Content-Type is a hint, not proof of safety.** A server can declare `image/png` yet return an HTML error page; it can also report the wrong charset or a malformed stream. When identifying file types, combine status, expected media type, magic bytes/checksum/signature, or an appropriate parser.

You can inspect the header:

~~~java
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("");

if (!contentType.startsWith("application/json")) {
    // Should not assume the body is the API's JSON.
}
~~~

This snippet is illustrative; header values may differ in case or have parameters, so production code should parse media types properly rather than using only case-sensitive `startsWith`. Headers are only one of the validation steps.

## 12. Size and Resource Management

**`ofString` and `ofByteArray`** are convenient but carry risks when responses are too large:
- A 100 MB response can create many allocations, higher than the raw payload size due to String/byte arrays and intermediates.
- Many concurrent requests sharply increase total memory pressure.
- `Content-Length` may be absent, wrong, or may not describe the size after content coding; do not rely solely on one header to block malicious data.
- When a hard cap on total bytes is needed, look into a custom subscriber or streaming with a counter and cancel/close when exceeding the threshold.

**`ofFile`** reduces the need to hold the entire body in the heap, but it is not "free":
- Disk can fill up, or quota/permissions can deny writes.
- A user-supplied destination can overwrite sensitive files if uncontrolled.
- Temp files can be left behind when a request fails.
- Use validated paths, enforce space/quota limits, and only publish files after validation.
- Writing to a temp file then renaming/moving per policy is better than writing directly to a file currently in use by users.

**`discarding`** avoids materializing the body in Java objects but does not avoid server/network cost. If only metadata is needed and the server allows it, HEAD can be used; if the response value is needed, discarding is the wrong choice because no body remains to parse.

**Observability tip:** log method, sanitized URI, status, content-type, duration, byte count, and handler choice; avoid logging plaintext bodies, tokens, Authorization headers, Cookies, and unnecessary personal information.

## 13. Timeouts, Network Errors, and Filesystem Errors

The four handlers do not replace timeout policies:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

This is a snippet. `connectTimeout` applies to establishing a new connection; request timeout applies to the request at the API level. If a request fails after the server has already processed it, do not automatically assume retrying is safe, especially for non-idempotent POSTs.

**Distinguishing causes:**
- Valid HTTP 404/500 → `HttpResponse<T>` with the corresponding `statusCode()`.
- DNS/connect/TLS/transport error → `IOException` (or exceptional completion in `sendAsync`).
- Request timeout → `HttpTimeoutException`; connect timeout → `HttpConnectTimeoutException` when applicable.
- Thread interrupted during `send` → `InterruptedException`; restore the interrupt flag if handling in a method with such a policy.
- Unwritable file destination/disk error with `ofFile` → I/O failure, possibly leaving a partial file that needs cleanup.

Not every `IOException` means the server has not received the request. Especially when downloading or making requests with side effects, design retry/idempotency and cleanup explicitly.

## 14. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `ofString` for images/PDF/binary | Corrupt data decoding | `ofByteArray` or `ofFile` |
| Using `ofByteArray` for multi-GB files | Heap pressure/OOM | `ofFile` or streaming |
| Confusing `HttpResponse<String>` with `HttpResponse<byte[]>` | Compile/type mismatch | Type `T` must match the handler |
| Thinking `BodyPublisher` is a response handler | Code going the wrong direction | Publisher for request, handler for response |
| Forgetting to set charset when API specifies UTF-8 | Garbled characters on some servers | `ofString(UTF_8)` or handle header intentionally |
| Believing `ofString()` always uses OS encoding | Misunderstanding decoding | Java 17 uses charset from Content-Type, falling back to UTF-8 |
| Calling `new String(bytes)` without choosing a charset | Text may not be portable | Use `new String(bytes, UTF_8)` when matching the contract |
| Thinking `ofFile(path)` auto-truncates old files | Old trailing bytes remain | Use `TRUNCATE_EXISTING` or `CREATE_NEW` |
| Thinking `ofFile` auto-checks HTTP 2xx | Saves 404 HTML as a valid file | Check status/type/checksum before publishing |
| Using an unchecked path from Content-Disposition | Path traversal/overwriting | Pick your own path, validate filename, quarantine |
| Thinking `discarding()` is equivalent to HEAD | Server may still transmit the body | Use HEAD when API allows, or discard intentionally |
| Thinking `discarding()` means HTTP 204 | Wrong semantics | `HttpResponse<Void>.body()==null` is due to the handler, not status |
| Not cleaning up failed/partial files | Disk clutter or serving incomplete data | Delete temp, check errors, atomic replace when feasible |
| Not limiting body input | DoS via RAM/disk | Quotas, size caps, streaming/custom handler |
| Believing every 404 must throw IOException | Incorrect HTTP error handling | Check `statusCode()` |
| Ignoring Future exceptions in `sendAsync` | Network/file errors swallowed | Handle exceptional completion and cleanup |
| Logging the entire response body | Leaking confidential data | Sanitized logging, limit content |
| Reading an entire large file back into RAM after `ofFile` | Loses the benefit of saving to file | Process via streaming or file APIs |

## 15. Self-Check Exercises

**1.** What `HttpResponse<T>` types do the four handlers return?  
**Answer:** `ofString` → `HttpResponse<String>`; `ofByteArray` → `HttpResponse<byte[]>`; `ofFile` → `HttpResponse<Path>`; `discarding` → `HttpResponse<Void>`.

**2.** How does `ofString(StandardCharsets.UTF_8)` differ from `ofString()`?  
**Answer:** The parameterized version uses the explicitly chosen charset; the no-argument version reads the charset from Content-Type if present/supported, falling back to UTF-8 in Java 17.

**3.** A byte FF appears as `-1` in `byte[]`. Is there a network error?  
**Answer:** No. Java byte is signed; use `bytes[i] & 0xff` to get the unsigned value.

**4.** Why not use `ofByteArray()` to download a 5 GB file?  
**Answer:** It accumulates bytes on the heap, which can cause OOM; save to a file/stream with appropriate quotas.

**5.** Does `BodyHandlers.ofFile(path)` automatically truncate a previously longer file?  
**Answer:** No. The default is equivalent to `CREATE, WRITE`. Use `TRUNCATE_EXISTING` explicitly if you want to replace content, or `CREATE_NEW` if overwriting is forbidden.

**6.** Does receiving HTTP 404 with `ofFile(path)` automatically reject saving?  
**Answer:** No. The handler is designed to accept the body regardless of status; the application checks the response and may have to delete the file.

**7.** Is `discarding()` returning `body() == null` with HTTP 202 normal?  
**Answer:** Yes. The body type is `Void` and the content is discarded.

**8.** Does `discarding()` eliminate all network traffic of the response?  
**Answer:** No. Server/client still process the response on the wire; it only avoids keeping the body as a result.

**9.** When `BodyHandlers.ofFile()` completes successfully, what is `response.body()`?  
**Answer:** A `Path` pointing to the file to which the body was written according to the contract.

**10.** Does `ofInputStream()` have the same lifecycle as `ofString()`?  
**Answer:** No. A streaming handler can return the response before the body is completely read; the caller must read/close the stream.

**11.** Why is `Content-Type: application/pdf` not enough to trust that a downloaded file is a valid PDF?  
**Answer:** A header is not proof; you need to check status, signature/magic bytes, size/hash, or a parser depending on the security level.

**12.** If `sendAsync(request, ofFile(path))` returns an uncompleted Future, has the file been published yet?  
**Answer:** It should not be. Wait for completion, check response status and data; the temp file may still be in the process of being created/written.

## 16. Official References

- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): the four factory methods, `ofFile` open options, default charset, and the rule of not automatically inspecting HTTP status.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `HttpResponse<T>`, status, headers, body, and response info.
- [Java SE 17 — HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): how to select a subscriber based on response metadata.
- [Java SE 17 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): body subscribers and completion semantics.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, timeouts, and HTTP client lifecycle.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE`, `CREATE_NEW`, `WRITE`, `TRUNCATE_EXISTING`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): creating temp files, checking size, moving/cleaning up files.
- [Java SE 17 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): small HTTP server only for serving localhost test fixtures.