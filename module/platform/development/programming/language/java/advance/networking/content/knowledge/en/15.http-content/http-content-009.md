# Choosing a BodyHandler by Status and Headers Instead of Receiving Every Body by Default in Java HttpClient

## 1. The problem: not every HTTP response body should be loaded into memory

When calling Java `HttpClient`, the most common way to write it is:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

This is convenient for small, trusted responses. However, if the server returns **404 with a very long HTML page**, **200 with a large binary file**, **204 with no content**, or **200 with a `Content-Type` that is not the format the application needs**, should you collect all bytes into a `String` by default?

**No.** Java 17 provides `HttpResponse.BodyHandler<T>` so that an application can **choose how to receive the body based on the status code and response headers right after the headers arrive, before reading the body**. This is the key mechanism that separates **the decision of whether to accept/transform/save to file/discard the body** from the actual work of consuming the bytes.

~~~text
HttpClient sends HttpRequest
              |
              v
HTTP response: status + headers received
              |
              v
BodyHandler<T>.apply(ResponseInfo info)
   |                |                      |
   | 200 + text     | 404/204/304          | 200 + binary
   v                v                      v
BodySubscriber      BodySubscriber         BodySubscriber
.ofString(UTF_8)    .replacing(...)        .ofFile(...) / .ofInputStream()
   |                |                      |
   v                v                      v
String/typed T      do not keep body       file/stream/typed T
              \       |                    /
               \      |                   /
                v     v                  v
                 HttpResponse<T>
~~~

That means `BodyHandler` is the **strategy selector**, while `BodySubscriber` is the **consumer of bytes from the HTTP stream**. `BodyHandler` is not the place where the body already exists for parsing JSON, nor should it call a database or wait on heavy tasks.

This lesson belongs to **Java Advance - networking → HTTP Content**, focusing on the topic **“Choosing a BodyHandler by status and headers instead of receiving every body by default”**, without going deep into writing an HTTP parser or building an HTTP stack from scratch.

## 2. Learning objectives

After this lesson, you will be able to:

1. Distinguish `HttpResponse.BodyHandler<T>`, `HttpResponse.ResponseInfo`, `HttpResponse.BodySubscriber<T>`, and `HttpResponse<T>`.
2. Know the **timing** when the `BodyHandler.apply()` callback receives status, headers, and version, and why the body has not been read yet.
3. Choose to discard a body using `BodySubscribers.replacing(value)` or `discarding()` instead of unconditionally using `BodyHandlers.ofString()` / `ofByteArray()`.
4. Check `statusCode()`, `Content-Type`, `Content-Length`, no-content statuses, and HTTP rules before choosing a `BodySubscriber`.
5. Use `BodySubscribers.mapping()` so that different branches still return **the same Java type `T`**, avoiding generic type errors.
6. Use `BodySubscribers.ofString(UTF_8)` for **small accepted text content**, `ofFile` for controlled downloads, and `ofInputStream` for streaming processing.
7. Understand that `Content-Length` is **peer-supplied metadata**, which may be missing or wrong; it is **not an actual byte limit**.
8. Distinguish “discarding the body” from “not receiving bytes from the network”, along with the consequences for connection reuse and streaming resource lifecycle.
9. Run two complete Java 17+ programs: filtering text by status/type/length and saving a file only from valid responses.
10. Design tests for error statuses, unexpected media types, missing length, large payloads, responses with no body, timeouts, retries, redirects, and security.

## 3. Core API: when is BodyHandler called?

The main types of the `java.net.http` module:

~~~java
HttpResponse.BodyHandler<T> handler;
HttpResponse.ResponseInfo info;
HttpResponse.BodySubscriber<T> subscriber;
HttpResponse<T> response;
~~~

These are **conceptual declarations**, not a standalone runnable program. In real code, `BodyHandler<T>` is a **functional interface**:

~~~java
@FunctionalInterface
public interface BodyHandler<T> {
    BodySubscriber<T> apply(ResponseInfo responseInfo);
}
~~~

The signature above is a condensed description for learning; you do not need to re-declare the interface already provided by the JDK. `apply` takes a `ResponseInfo` and **returns** a `BodySubscriber<T>`; Java `HttpClient` then uses the subscriber to process the body. `ResponseInfo` provides:

| Method | Value | When to use |
| --- | --- | --- |
| `info.statusCode()` | `int`, e.g. `200`, `204`, `404` | Prioritize checking status first; decide whether to keep an error body |
| `info.headers()` | `HttpHeaders` | Inspect `Content-Type`, `Content-Length`, `Content-Disposition`... |
| `info.version()` | `HttpClient.Version` | Actual HTTP version of the response |
| `info.headers().firstValue("Content-Type")` | `Optional<String>` | Only a header value, may be missing |
| `info.headers().firstValueAsLong("Content-Length")` | `OptionalLong` | May be empty; **may throw NumberFormatException** if unparseable |

**Important:** `apply(info)` runs **after the status line/response headers are ready, but before body bytes are read/consumed by the subscriber**. Therefore, you can enforce a policy early without allocating a huge `byte[]` first and checking the status afterward.

A simple custom handler:

~~~java
HttpResponse.BodyHandler<String> handler = info -> {
    if (info.statusCode() != 200) {
        return HttpResponse.BodySubscribers.replacing("");
    }
    return HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
};
~~~

This is a **code snippet** inside a method that imports `java.net.http.HttpResponse` and `java.nio.charset.StandardCharsets`. For status 200, the body is read as a `String`. For non-200 statuses, the JDK **consumes and discards the body** and returns an empty `String` that you chose; it **does not automatically throw an HTTP exception**.

### 3.1. BodyHandler and BodySubscriber are not the same thing

- `BodyHandler<T>` receives **metadata**, chooses how to handle the body, and **creates a `BodySubscriber<T>` for the exchange**.
- `BodySubscriber<T>` receives **lists of `ByteBuffer`s of the body** according to `Flow.Subscriber<List<ByteBuffer>>`, returning a `CompletionStage<T>` from `getBody()`.
- `BodyHandlers.ofString()` is a **built-in handler** and will use the corresponding subscriber.
- `BodySubscribers.ofString(UTF_8)` is a **built-in subscriber** for a custom handler to return.
- `HttpResponse<T>.body()` is the **result of type T**, depending on the subscriber; it can be `String`, `Path`, `InputStream`, `Void`, or a mapped domain type.
- `HttpResponse.statusCode()` is metadata after the response is received; it does **not** change the decision already made in the handler.

In a custom handler, you typically **return `BodySubscribers.*`**, not `BodyHandlers.*`. The two factory groups differ in type; confusing them causes a common compile error.

### 3.2. BodyHandler decides before the body, not after the body

~~~text
Headers arrive: 200 | Content-Type: application/json | Content-Length: 12
                           |
                           v
                  BodyHandler decides
                           |
                           v
                  Body bytes start arriving
                           |
                           v
               BodySubscriber consumes / maps
                           |
                           v
                  HttpResponse<T>.body()
~~~

Therefore, the handler cannot inspect parsed JSON content to decide “should I download this JSON?”. It only knows information **from the status and headers**. If a decision must depend on actual data, perform **validation while consuming** or choose a bounded streaming subscriber.

## 4. Why might default ofString/ofByteArray be unsuitable?

The convenience handlers:

~~~java
HttpResponse.BodyHandlers.ofString();
HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8);
HttpResponse.BodyHandlers.ofByteArray();
HttpResponse.BodyHandlers.discarding();
HttpResponse.BodyHandlers.ofFile(file);
HttpResponse.BodyHandlers.ofInputStream();
~~~

This is a **list of expressions** (the `file` variable must exist beforehand, along with relevant imports). `BodyHandlers` are explicitly documented by the JDK: the built-in implementations generally **do not check the status code**, meaning **the body is accepted according to the chosen strategy**, even for 404 or 500 responses. Consequently:

- `ofString()`: accumulates bytes and creates a `String`; if used on an endpoint with unbounded payloads, it risks consuming a large amount of heap.
- `ofByteArray()`: holds the entire body as a `byte[]`; similar risk.
- `ofFile(path)`: writes the response body to disk; **does not automatically skip a 404 HTML error page** and can accidentally write an error page under the name `report.pdf` if unchecked.
- `ofInputStream()`: lets the caller read the stream; **must read to EOF or close the stream** to release the exchange properly according to the contract.
- `discarding()`: does not retain content, yet **still processes/drains the incoming body**; it does not mean “the client receives zero bytes at all”.
- `replacing(value)`: discards incoming bytes and uses **the provided value of type T**, which is well suited for the skip branch in a custom policy.

**The goal** is not “every 4xx/5xx must discard its body”. An API may return useful error JSON following RFC 9457 Problem Details; we only need to **choose in a controlled way**: if you want to read the error, use a strategy that keeps a small, bounded error snippet rather than keeping everything by default.

## 5. Decision table by status and headers

| Status and headers | Potentially reasonable choice | Reason / notes |
| --- | --- | --- |
| `200 OK`, `Content-Type: application/json`, small body, sufficiently trusted | `ofString(UTF_8)` then validate JSON | Only use when there is a real byte limit |
| `200 OK`, `text/plain`, small size | `ofString(UTF_8)` | Only text if the response has valid semantics/charset |
| `200 OK`, `application/octet-stream` to download | `ofFile(controlledPath)` | Disk path is decided by the **application**, with quota and cleanup |
| `200 OK`, binary/unknown length but allowed to read incrementally | `ofInputStream()` or streaming subscriber | Read with a byte budget, must close/cancel |
| `201 Created` with valid JSON | Can accept a small body | Do not hardcode all successes as `status == 200` |
| `202 Accepted` with metadata/job URI | Can accept small JSON | `202` has different semantics from business completion |
| `204 No Content` | `replacing(NO_BODY)` / `discarding()` | No content according to HTTP semantics |
| `304 Not Modified` | `replacing(NO_BODY)` / `discarding()` | Use existing metadata/cache, do not expect a new body |
| Response to `HEAD` | Do not read body, still inspect headers | `HEAD` has no response content even though metadata may resemble GET |
| `3xx` when not auto-following redirects | Discard or handle intermediate content in a controlled way | Inspect `Location` and redirect policy |
| `400`–`499` | May discard or keep a **bounded** error body | Status is the primary basis; API errors sometimes return useful JSON |
| `500`–`599` | Discard or take a small error excerpt | Avoid writing large error pages to a download file |
| `206 Partial Content` | Handle specially when you **requested a Range** | Inspect `Content-Range` and assemble at the right offset |
| Missing `Content-Length` | Can stream with a hard cap, or fail-closed | Header may be absent with chunked transfer/HTTP2 |
| Very large `Content-Length` | Refuse to store in unbounded memory/file | Header is a hint, not a hard cap |
| Wrong/unexpected `Content-Type` | Discard, report error, or appropriate fallback | `Content-Type` is received data; still must validate actual content |

**Note on HTTP semantics:** 204/304 responses or `HEAD` responses do not have content to consume like a normal GET. 1xx statuses are typically informational before the final response; in normal `HttpClient` flows, do not confuse `100 Continue` with a final response body to parse as JSON. `205 Reset Content` also specifies not generating content according to the standard; if a policy applies to all “no-content” responses, consider 205 as well.

### 5.1. Check status before checking content type

A 404 error page may be returned by a server with `Content-Type: application/json`. If you only look at `Content-Type` and parse the JSON into a business-success object, your logic can break. Check status first:

~~~java
if (info.statusCode() < 200 || info.statusCode() >= 300) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("SKIP_STATUS", ""));
}
~~~

This is a **code snippet** inside a `BodyHandler<Choice>` lambda, where `Choice` is the record in the Section 8 example. This policy discards all non-2xx responses, including error bodies; for production systems that need error details, build a **separate error branch** with a bounded body. Not all 2xx responses have content: 204/205 must be handled separately.

### 5.2. Content-Type header requires understanding media type and parameters

Examples:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Type: application/json
Content-Type: application/problem+json
Content-Type: application/octet-stream
~~~

If the policy accepts text:

- Compare media type **case-insensitively**, stripping `; charset=...` parameters before comparing.
- `application/problem+json` has a JSON-like structure but different semantics from regular `application/json`: it should have a separate error-handling policy.
- The header may be missing or misdeclared; **do not** use a text type as proof that data is safe/validated.
- The actual charset must match the API contract. JSON exchanged on the web commonly uses UTF-8; `text/plain` may declare a charset. Hardcoding a charset in a demo is fine because we control the server, not something to apply blindly to every site.
- For downloaded files, `Content-Type` is not an antivirus, checksum, or guarantee of file format. Always validate bytes if the business logic requires it.

**Why strip the media type?** `"text/plain; charset=UTF-8".equals("text/plain")` is false, yet both headers share the same media type. You can take the part before `;`, trim it, and lower-case it using `Locale.ROOT` for a demo. A production parser needs to handle valid field values and malformed/duplicate cases according to the HTTP stack.

### 5.3. Content-Length is a byte count, but untrustworthy as a hard barrier

`Content-Length` is the **number of octets** in the body per HTTP rules, not `String.length()`. `HttpHeaders.firstValueAsLong("Content-Length")` returns an `OptionalLong` if a parseable value is present, **empty if absent**, and **may throw `NumberFormatException`** if the value cannot be parsed.

~~~java
OptionalLong length;
try {
    length = info.headers().firstValueAsLong("Content-Length");
} catch (NumberFormatException invalid) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("SKIP_LENGTH", ""));
}
if (length.isEmpty() || length.getAsLong() > 64) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("SKIP_LENGTH", ""));
}
~~~

This is a **code snippet** inside an example handler. Even when checking `<= 64` and trusting that the server follows the contract, there are several limitations:

1. `Content-Length` **does not always appear**, for example in HTTP/1.1 chunked or streamed responses.
2. The header **may be wrong** if the peer or an intermediary is untrusted, or if a message has framing errors.
3. `Content-Encoding: gzip` can make the decoded data size **differ** from the number of bytes sent on the wire; you need a post-decoding limit if using decompression.
4. `Content-Length` does not prevent `ofString()` or `ofFile()` from storing more bytes if the sender misbehaves and the stack allows it; relying only on the header is **not a defense against memory/disk exhaustion**.
5. You need **actual limits while reading**: byte counters, timeouts, max decoded size, disk quota, Flow cancellation, or proxy/server enforcement.

That is why the demos use a **controlled local server**. Production systems should enforce a **hard cap in the subscriber/stream**, and use `Content-Length` as an **early filter** step.

## 6. Generic type T: the same BodyHandler must return BodySubscriber<T>

The `client.send(request, bodyHandler)` method has a signature parameterized by the generic body type:

~~~java
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;
~~~

This is an API signature illustration (not an executable call). If a handler has type `BodyHandler<String>`, every branch must return `BodySubscriber<String>`; you cannot have one branch return `BodySubscriber<Void>` and another return `BodySubscriber<Path>` and expect the compiler to infer a union type.

**Wrong type:**

~~~java
// WRONG: lambda declares BodyHandler<String>,
// but the 404 branch returns BodySubscriber<Void>.
HttpResponse.BodyHandler<String> wrong = info ->
        info.statusCode() == 404
                ? HttpResponse.BodySubscribers.discarding()
                : HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8);
~~~

This example is **intentionally non-compiling** to illustrate a generic mismatch, not a runnable Java program.

**Correct using `replacing`:**

~~~java
HttpResponse.BodyHandler<String> correct = info ->
        info.statusCode() == 404
                ? HttpResponse.BodySubscribers.replacing("")
                : HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8);
~~~

This is a Java 17 code snippet; import `HttpResponse` and `StandardCharsets`. `replacing("")` is a `BodySubscriber<String>`, consistent with `ofString(...)`. If you need to distinguish “discarded” from “valid empty body”, use a **record/result type** containing a `decision` instead of returning `""` and guessing its meaning.

### 6.1. Using mapping to return a clear domain type

~~~java
record Choice(String decision, String text) {}

HttpResponse.BodySubscriber<Choice> kept =
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8),
                text -> new Choice("ACCEPT_TEXT", text));

HttpResponse.BodySubscriber<Choice> dropped =
        HttpResponse.BodySubscribers.replacing(
                new Choice("SKIP_STATUS", ""));
~~~

These are code snippets inside a class/method, not standalone. Both branches return **`BodySubscriber<Choice>`**. `mapping` lets you convert a `String` into a `Choice` **after the body has been processed by the upstream subscriber**.

**Performance note:** the JDK documentation states that the mapping function runs on **the `HttpClient`'s executor**. Do not put database calls or long blocking I/O inside the mapper; if you want to stream large JSON/files, offload to a separate asynchronous/streaming parsing mechanism and keep the executor responsive.

## 7. Concrete strategies: discard, accept text, write to file, or stream?

| Factory in custom handler | Returned body type | Typical condition | Risks / cleanup |
| --- | --- | --- | --- |
| `BodySubscribers.replacing(value)` | Depends on `value` of type `T` | Discard unacceptable response, still return a clear result | Still drains incoming bytes; does not block network traffic |
| `BodySubscribers.discarding()` | `Void` | Only need status/headers, do not need body | Generic `Void`, response body is null |
| `BodySubscribers.ofString(UTF_8)` | `String` | Small text after validating status/type/size | Accumulates entire body on heap, needs hard cap |
| `BodySubscribers.ofByteArray()` | `byte[]` | Small bounded binary payload | Heap grows with actual received body |
| `BodySubscribers.ofFile(path)` | `Path` | Allowed download, app-controlled path | Disk quota, symlinks, path ownership, partial file cleanup |
| `BodySubscribers.ofInputStream()` | `InputStream` | Streaming read/enforcing limit when `Content-Length` is absent | Must read to EOF or `close()` |
| `BodySubscribers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Reactive/backpressure pipeline | Subscribe exactly once, consume/cancel in a controlled way |
| `BodySubscribers.mapping(upstream, fn)` | `U` | Convert `String`/`Path`/`Void` to a unified result | Mapper may run on the client executor |
| `BodySubscribers.fromSubscriber(...)` | Depends on `T` | Need an app-controlled `Flow` subscriber | Must follow the `Flow` protocol and cancellation properly |

**Important:** `replacing`/`discarding` prevents the application from **retaining the whole body in a `String`/`byte[]`/file**, but it does **not** guarantee that the server will not send the body or that bandwidth will not be consumed. The JDK often has to consume/drain the body to comply with framing and may keep the connection for reuse. If you want to abort because a response is too large or untrusted, you need cancellation/closing at the streaming/subscriber level according to policy; connection reuse behavior may be affected.

## 8. Standalone runnable program #1: filtering by status, Content-Type, and Content-Length

### 8.1. Program policy

A local HTTP server creates seven reproducible scenarios:

- `/ok`: 200 + `text/plain` + 5 bytes → **ACCEPT_TEXT**.
- `/json`: 200 + `application/json` + 11 bytes → **ACCEPT_TEXT**.
- `/error`: 404 + text → **SKIP_STATUS** (even though a body exists).
- `/binary`: 200 + `application/octet-stream` → **SKIP_TYPE**.
- `/large`: 200 + 100-byte text → **SKIP_LENGTH**, because the demo limit is 64 bytes.
- `/empty`: 204 No Content → **NO_BODY**.
- `/unknown`: 200 + chunked text with no `Content-Length` → **SKIP_LENGTH** (the demo's fail-closed policy).

The code **does not load rejected responses into the heap**, because it uses `BodySubscribers.replacing(...)`. For accepted text, it uses `BodySubscribers.ofString(UTF_8)` via `mapping(...)`. This is a **metadata-based filter**, not an absolute quota against malicious payloads: if a server declares a small `Content-Length` but sends a huge actual body, you need a streaming subscriber that enforces bytes as in Section 10.

Create file **`SelectiveBodyHandlerDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.OptionalLong;

public class SelectiveBodyHandlerDemo {
    record Choice(String decision, String text) {}

    static HttpResponse.BodyHandler<Choice> selectBody() {
        return info -> {
            int status = info.statusCode();
            if (status == 204 || status == 304) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("NO_BODY", ""));
            }
            if (status < 200 || status >= 300) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_STATUS", ""));
            }

            String type = info.headers().firstValue("Content-Type")
                    .orElse("").split(";", 2)[0]
                    .trim().toLowerCase(Locale.ROOT);
            if (!type.equals("text/plain") &&
                !type.equals("application/json")) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_TYPE", ""));
            }

            OptionalLong length;
            try {
                length = info.headers().firstValueAsLong("Content-Length");
            } catch (NumberFormatException invalid) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_LENGTH", ""));
            }
            if (length.isEmpty() || length.getAsLong() < 0 ||
                    length.getAsLong() > 64) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_LENGTH", ""));
            }

            return HttpResponse.BodySubscribers.mapping(
                    HttpResponse.BodySubscribers.ofString(
                            StandardCharsets.UTF_8),
                    text -> new Choice("ACCEPT_TEXT", text));
        };
    }

    static void reply(HttpExchange exchange, int status,
                      String type, String text) throws IOException {
        try (exchange) {
            if (type != null) {
                exchange.getResponseHeaders().set("Content-Type", type);
            }
            if (status == 204) {
                exchange.sendResponseHeaders(status, -1);
                return;
            }
            byte[] payload = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, payload.length);
            exchange.getResponseBody().write(payload);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ok", e ->
                reply(e, 200, "text/plain; charset=UTF-8", "hello"));
        server.createContext("/json", e ->
                reply(e, 200, "application/json", "{\"ok\":true}"));
        server.createContext("/error", e ->
                reply(e, 404, "text/plain", "not allowed"));
        server.createContext("/binary", e ->
                reply(e, 200, "application/octet-stream", "BYTE"));
        server.createContext("/large", e ->
                reply(e, 200, "text/plain", "x".repeat(100)));
        server.createContext("/empty", e ->
                reply(e, 204, null, ""));
        server.createContext("/unknown", e -> {
            try (e) {
                e.getResponseHeaders().set("Content-Type", "text/plain");
                e.sendResponseHeaders(200, 0); // chunked: no Content-Length
                e.getResponseBody().write("chunk".getBytes(
                        StandardCharsets.UTF_8));
            }
        });
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            for (String path : new String[]{
                    "/ok", "/json", "/error", "/binary",
                    "/large", "/empty", "/unknown"}) {
                URI uri = URI.create("http://127.0.0.1:" +
                        server.getAddress().getPort() + path);
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5))
                        .GET().build();
                HttpResponse<Choice> response = client.send(
                        request, selectBody());
                System.out.println(path + " -> " + response.statusCode()
                        + " | " + response.body().decision()
                        + " | " + response.body().text());
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile targeting **Java 17** APIs and run:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver SelectiveBodyHandlerDemo.java
java --add-modules jdk.httpserver SelectiveBodyHandlerDemo
~~~

**Stdout verified on OpenJDK 24 with `javac --release 17`:**

~~~text
/ok -> 200 | ACCEPT_TEXT | hello
/json -> 200 | ACCEPT_TEXT | {"ok":true}
/error -> 404 | SKIP_STATUS | 
/binary -> 200 | SKIP_TYPE | 
/large -> 200 | SKIP_LENGTH | 
/empty -> 204 | NO_BODY | 
/unknown -> 200 | SKIP_LENGTH | 
~~~

The trailing space on the skipped lines comes from `System.out.println(... + " | " + response.body().text())` with `text=""`; it is **not** an actual received body stored in `Choice`.

### 8.2. Request-by-request flow analysis

**Case `/ok`:**

1. `ResponseInfo.statusCode() == 200`, not skipped by status.
2. `Content-Type: text/plain; charset=UTF-8` has its media type extracted as `text/plain`.
3. `Content-Length: 5` is within `0..64`.
4. The handler returns `BodySubscribers.mapping(ofString(UTF_8), ...)`.
5. The body bytes are decoded into `"hello"` and mapped to `Choice("ACCEPT_TEXT", "hello")`.

**Case `/error`:**

1. The handler sees `404` before having to read the body into a `String`.
2. Returns `BodySubscribers.replacing(new Choice("SKIP_STATUS",""))`.
3. The response still has `statusCode()==404` for the application layer to handle.
4. The error payload sent by the server is still **discarded/consumed** by the JDK, but the application does not keep the body in `Choice`/heap.

**Case `/binary`:** status 200 but `Content-Type` is not in the allowlist; `ofString` is not called to create a meaningless string from binary data.

**Case `/large`:** the header reports 100 bytes, so the handler skips early. **There is no actual hard cap** in this snippet; it relies only on the local server's header.

**Case `/empty`:** status 204 carries no content; the handler returns Choice `NO_BODY` without attempting to decode a `String`.

**Case `/unknown`:** Java `HttpServer` sends HTTP/1.1 chunked when `sendResponseHeaders(200, 0)` is called, with no `Content-Length`; the demo policy chooses to **skip** instead of automatically saving a payload of unknown length. Real applications can choose bounded streaming rather than discarding every body without a length header.

### 8.3. Why do we need the Choice type?

If you return an empty `String` when discarding a body, it is hard for the caller to distinguish:

- A 200 response whose actual body is an empty string.
- A 204 response with no body per semantics.
- A 404 response that was discarded.
- A 200 binary response that was rejected.
- A 200 long-body response that was rejected by policy.

`record Choice(String decision, String text)` makes the decision **explicit**, helping logging, fallback handling, and testing stay unambiguous. In production, you can replace it with `sealed interface Result permits Text, Skipped, Downloaded` or a record holding a `Decision` enum and metadata, as long as they share the same generic `T`.

## 9. Standalone runnable program #2: write to file only when status and headers match

A common mistake:

~~~java
HttpResponse<Path> response = client.send(
        request, HttpResponse.BodyHandlers.ofFile(Path.of("report.pdf")));
~~~

Even if the endpoint returns a **404 HTML error page**, the `ofFile` handler still processes the body according to its file-writing policy. It may create `report.pdf` containing error content instead of a real PDF. If you need a controlled download, choose **`ofFile` only in the accepted branch**.

Next example:

1. A local `/asset` endpoint returns HTTP 200, `application/octet-stream`, and exactly **8 binary bytes**.
2. `/missing` returns HTTP 404 while also setting `application/octet-stream` → **no file created**.
3. `/text` returns HTTP 200 but `text/plain` → **no file created**.
4. The handler uses `BodySubscribers.replacing(new Outcome(..., null))` for skip branches.
5. The accepted branch uses `BodySubscribers.ofFile(target, CREATE_NEW, WRITE)` and then `mapping` to `Outcome`.
6. Each request has a **target file path generated by the application inside a private temporary directory**, never taking the filename from the server.
7. At the end of the program, it deletes the files it manages and the temporary directory.

**File: `SelectiveFileDownloadDemo.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.Locale;
import java.util.OptionalLong;

public class SelectiveFileDownloadDemo {
    record Outcome(String decision, Path file) {}

    static HttpResponse.BodyHandler<Outcome> forDownload(Path target) {
        return info -> {
            if (info.statusCode() != 200) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_STATUS", null));
            }
            String mediaType = info.headers().firstValue("Content-Type")
                    .orElse("").split(";", 2)[0]
                    .trim().toLowerCase(Locale.ROOT);
            if (!mediaType.equals("application/octet-stream")) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_TYPE", null));
            }
            OptionalLong size;
            try {
                size = info.headers().firstValueAsLong("Content-Length");
            } catch (NumberFormatException invalid) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_LENGTH", null));
            }
            if (size.isEmpty() || size.getAsLong() < 0 ||
                    size.getAsLong() > 1_024) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_LENGTH", null));
            }
            return HttpResponse.BodySubscribers.mapping(
                    HttpResponse.BodySubscribers.ofFile(target,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE),
                    file -> new Outcome("SAVED", file));
        };
    }

    static void reply(HttpExchange exchange, int status,
                      String contentType, byte[] bytes) throws IOException {
        try (exchange) {
            exchange.getResponseHeaders().set("Content-Type", contentType);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("http-download-");
        Path ok = directory.resolve("ok.bin");
        Path missing = directory.resolve("missing.bin");
        Path wrong = directory.resolve("wrong.bin");
        HttpServer server = null;
        try {
            server = HttpServer.create(
                    new InetSocketAddress(
                            InetAddress.getByName("127.0.0.1"), 0), 0);
            server.createContext("/asset", e -> reply(e, 200,
                    "application/octet-stream",
                    new byte[]{1,2,3,4,5,6,7,8}));
            server.createContext("/missing", e -> reply(e, 404,
                    "application/octet-stream", new byte[]{9,9,9}));
            server.createContext("/text", e -> reply(e, 200,
                    "text/plain", new byte[]{65,66}));
            server.start();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            for (String path : new String[]{"/asset","/missing","/text"}) {
                Path destination = path.equals("/asset") ? ok :
                        path.equals("/missing") ? missing : wrong;
                URI uri = URI.create("http://127.0.0.1:" +
                        server.getAddress().getPort() + path);
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5)).GET().build();
                HttpResponse<Outcome> response = client.send(
                        request, forDownload(destination));
                System.out.print(path + " -> " + response.statusCode() +
                        " | " + response.body().decision());
                if (response.body().file() != null) {
                    System.out.println(" | bytes=" +
                            Files.size(response.body().file()));
                } else {
                    System.out.println(" | file=" + Files.exists(destination));
                }
            }
        } finally {
            if (server != null) server.stop(0);
            Files.deleteIfExists(ok);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(wrong);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Java 17+ run commands:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver SelectiveFileDownloadDemo.java
java --add-modules jdk.httpserver SelectiveFileDownloadDemo
~~~

**Stdout verified with OpenJDK 24 and `--release 17`:**

~~~text
/asset -> 200 | SAVED | bytes=8
/missing -> 404 | SKIP_STATUS | file=false
/text -> 200 | SKIP_TYPE | file=false
~~~

### 9.1. Why is no file created in the 404 or wrong-type branches?

The handler is called **once status and headers are available**, so right at that point it decides to return `replacing` instead of `ofFile`. Therefore `BodySubscribers.ofFile(...)` **is never instantiated for the rejected exchange**, and the application does not write the error body to the target file.

Correctness in the demo relies on:

- A controlled local endpoint whose header length matches the actual payload.
- The file path being created inside a temporary directory privately created by the program.
- `CREATE_NEW` preventing overwriting an existing target file (if the file exists, the download operation fails instead of truncating the file).
- Files being cleaned up in `finally` even if an exception occurs.

**Do not claim the demo is safe against a malicious server.** The `Content-Length <= 1024` header check is only a **filtering step**, not a hard disk quota. Production also needs limits on **actually received** bytes, verification of checksum/magic bytes/charset per file format, final size checks, protection against filename injection, path traversal, symlinks, disk exhaustion, and partial files when errors occur mid-transfer.

### 9.2. HTTP policy should depend on the resource type

A downloader that only accepts **200 OK** may be right if it wants a complete response. However, an application downloading files by ranges may need **206 Partial Content** and parse `Content-Range` to assemble file chunks at the right offset. If the server returns 301/302/307/308, you may need to follow redirects per policy and check the **final origin**; do not blindly move a file from any new origin into a trusted location. If the server returns 304 from a conditional GET, you need to use the stored cache instead of overwriting the old file with an empty one.

That means **choosing by status** must come from the **endpoint contract**, not by hardcoding “only 200 is valid” for every API.

## 10. When Content-Length is unknown: use streaming and enforce actual bytes

A body may lack a valid `Content-Length`, yet still be required JSON/text. If you do not want to discard it as in Example #1, you can choose **`BodySubscribers.ofInputStream()`** instead of `ofString()`, and then read with a limit in the caller.

Illustrative snippet (placed in a method where `client` and `request` already exist; requires `java.io.InputStream`, `java.io.IOException`, `java.net.http.*`, and `StandardCharsets`):

~~~java
HttpResponse.BodyHandler<InputStream> streaming = info -> {
    boolean text200 = info.statusCode() == 200 &&
            info.headers().firstValue("Content-Type")
                    .orElse("").toLowerCase(Locale.ROOT)
                    .startsWith("text/plain");
    if (!text200) {
        return HttpResponse.BodySubscribers.replacing(
                InputStream.nullInputStream());
    }
    return HttpResponse.BodySubscribers.ofInputStream();
};

HttpResponse<InputStream> response =
        client.send(request, streaming);

final int maxBytes = 64 * 1024;
try (InputStream body = response.body()) {
    byte[] bounded = body.readNBytes(maxBytes + 1);
    if (bounded.length > maxBytes) {
        throw new IOException("Body exceeds configured byte limit");
    }
    String acceptedText =
            new String(bounded, StandardCharsets.UTF_8);
    // Parse/validate acceptedText only after enforcing the byte limit.
}
~~~

This is a **code snippet**, not a standalone program. You also need to import `java.util.Locale`. `readNBytes(maxBytes + 1)` ensures the application **never holds more than `maxBytes + 1`** in this array, and then detects when the limit is exceeded; `try-with-resources` closes the stream. However, it **does not by itself protect** against a slow server that never finishes the body, a decompression bomb at another layer, or all types of resource exhaustion. You need request/stream deadlines, decoded byte limits if decompressing, connection limits, and a cancellation mechanism when limits are exceeded.

**Crucial lifecycle detail:** the JDK documentation notes that `BodySubscribers.ofInputStream()` completes the response **as soon as headers are read**, before the entire body is processed. The caller must **read all the way to EOF or call `InputStream.close()`**, otherwise it can hold onto connections/resources unnecessarily long.

With `BodySubscribers.ofPublisher()`, you must subscribe **once**, request properly, drain until `onComplete/onError`, or cancel when you no longer want to read; failing to subscribe can cause a leak. A custom subscriber must follow `Flow.Subscriber<List<ByteBuffer>>`, managing backpressure and cancellation. You should not push all blocking work into `BodySubscribers.mapping(...)`, because the mapper runs on the `HttpClient`'s executor and can cause starvation.

### 10.1. Header filtering + hard cap are two distinct layers

~~~text
LAYER 1 — HEADER DECISION:
  valid status?
  right media type?
  Content-Length <= policy (if present)?
     |
     v
LAYER 2 — BYTE ENFORCEMENT:
  stream/subscriber counts actual bytes
  stop/cancel when > limit
  timeout & decoded-size bound
     |
     v
LAYER 3 — SEMANTIC VALIDATION:
  charset / JSON schema / checksum / file format
  auth / business policy / move staged file
~~~

There is no reason to treat a `Content-Length: 100` header as a **certificate** that the body is only 100 bytes long. Nor should `Content-Type: application/json` be treated as valid parsed JSON. **The safe rule is to decide using headers, and verify using bytes and schema.**

## 11. HTTP cases with no body or unexpected bodies

### 11.1. HTTP 204, 205, 304, and HEAD

- `204 No Content`: successful response, but **has no content**.
- `205 Reset Content`: tells the client to reset the document/view and **must not generate content** per HTTP semantics.
- `304 Not Modified`: result of a conditional request; use the cached representation per rules, **no** new response content.
- Response to `HEAD`: no body even though headers may describe the representation as if GET were sent; `Content-Length` in a `HEAD` response must not be interpreted as “must download N bytes”.

A production selector may prioritize:

~~~java
boolean noContent = request.method().equals("HEAD") ||
        info.statusCode() == 204 ||
        info.statusCode() == 205 ||
        info.statusCode() == 304;
if (noContent) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("NO_BODY", ""));
}
~~~

This is a **code snippet** inside a lambda with access to an externally defined `request` and declared `Choice`. In a generic library handling multiple requests, pass the request context/method explicitly; `ResponseInfo` itself **does not contain the request method**. A 1xx response carries special semantics and is generally not processed as a final response with a body.

### 11.2. Error bodies are valuable, but should not be collected without bounds

An API may return errors following `application/problem+json`, for example:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Content-Length: 47

{"type":"about:blank","title":"Invalid data"}
~~~

This is a **format illustration**; the displayed `Content-Length` should not be used as the confirmed size for a real sent request without encoding and counting bytes accurately. If implementing a sample server, use `payload.getBytes(UTF_8).length` instead of typing the length by eye.

A reasonable policy:

- If a 4xx/5xx status has an allowed error media type, accept a **short error excerpt** with a **hard byte cap**, not unbounded.
- Do not log raw error bodies containing tokens/cookies/PII.
- Do not throw `IOException` by default just because HTTP status is 400/500; `HttpClient.send` can return a valid `HttpResponse` with that status.
- If the error body is not needed, use `replacing`/`discarding` to continue handling the status.
- When a response is returned via `sendAsync`, process the error and output data on an appropriate executor/consumer.

### 11.3. Content-Disposition does not determine a trusted path

When downloading an attachment, a server may send:

~~~text
Content-Disposition: attachment; filename="../../secrets.txt"
~~~

This is an example of an **untrusted value**. Do not pass the raw filename suggested by an HTTP header into `Path.resolve(...)` and open a file. Instead:

1. Use an application-owned directory with proper permissions.
2. Choose an application-decided filename or sanitize/whitelist carefully.
3. Prevent traversal, absolute paths, and symlinks.
4. Write to a separate staging file with `CREATE_NEW`, a hard size cap, and checksum/format validation.
5. After completion, move the file to its final location using an atomic move when supported by the system.
6. Clean up partial files when a download fails/cancels.

The JDK has `BodyHandlers.ofFileDownload(directory, ...)`, but if strict security is required, you need to understand how it handles filenames and still need an application policy; using `ofFile(controlledPath)` usually expresses ownership more clearly in this lesson.

## 12. sendAsync also selects the body by the same principles

`BodyHandler<T>` is passed to both APIs:

~~~java
HttpResponse<Choice> result = client.send(
        request, selectBody());

CompletableFuture<HttpResponse<Choice>> future =
        client.sendAsync(request, selectBody());
~~~

This is a **code snippet inside the `SelectiveBodyHandlerDemo` demo class**, requiring `java.util.concurrent.CompletableFuture` and the `client`/`request` variables. With `sendAsync`, `BodyHandler.apply(info)` still decides based on status/headers before the body subscriber consumes bytes. The difference is that **the caller does not block waiting for the response as with `send`**, but receives a `CompletableFuture`.

It does not mean Java automatically imposes a memory limit on `BodySubscribers.ofString` just because `sendAsync` is used. If many concurrent requests return large bodies, `ofString` can grow the heap very quickly. You need **admission control, concurrency limits, timeouts, and subscriber policies**, not just choosing an asynchronous API.

### 12.1. Immutability and thread-safety

A `BodyHandler<T>` may be used across multiple requests; you should not store shared mutable state without synchronization. Writing a lambda that only reads `info` and returns a new subscriber is usually simple and low-risk.

Do not reuse **a single `BodySubscriber` instance** across multiple HTTP exchanges. A subscriber has its own lifecycle/Flow subscription; create a new subscriber on each `apply(info)` call. File paths should also be separated per request to avoid two downloads writing to the same path.

## 13. Redirects, partial responses, and caching: when status matters more than body type

### 13.1. 3xx and redirect policy

Java `HttpClient` has a `followRedirects(...)` configuration. When redirects are followed automatically, the final response may come from a **different URI** with different headers/status. A selector chooses a subscriber based on the response info of the exchange being processed; the app should inspect `response.uri()`, `response.request()`, and `response.previousResponse()` if it needs to audit redirects.

If downloading from an initially trusted URL that redirects to an untrusted origin, inspecting only the final `Content-Type` is not enough. Origin/scheme/authorization policies must be controlled. Do not downgrade HTTPS to HTTP or vice versa without following security rules.

### 13.2. 206 Partial Content

If a request includes `Range` to resume downloading a file, a `206 Partial Content` response carries a partial representation; **do not** overwrite the entire file as with a normal 200. You need to verify `Content-Range`, ETag/validator, and total length/offset. Choose the `BodySubscriber` based on **status + request context + headers**.

### 13.3. 304 Not Modified

A conditional request may receive `304`. Returning an empty body choice is right, but the app must **combine it with the cached representation** according to HTTP caching semantics if it wants to display data. `304` should not be treated as an “empty error body” or “overwrite cached file with empty”.

## 14. Why is “choosing a subscriber” not a hard stop before downloading?

There are three easily confused concepts:

| Action | Meaning | Impact |
| --- | --- | --- |
| `BodySubscribers.replacing(value)` | **Consume/discard** bytes, return a value chosen by the app | Does not materialize body; network traffic still occurs |
| `BodySubscribers.ofInputStream()` + early close | App can read/cancel the remainder when it no longer wants the body | May close the connection, affecting reuse |
| Custom `Flow.Subscriber` cancels subscription | Stop receiving more data through the subscription per Flow contract | May abort the exchange/connection; state must be handled accurately |

Do not advertise `replacing` as “preventing the server from sending a 10 GB body”. If the server actually sends 10 GB, **draining/discarding still consumes bandwidth/time**, even though it saves heap/disk. When you want to cut off immediately because the body is untrusted, use cancellation/close/size limits and accept the connection-reuse trade-off.

Conversely, **discarding a response body by abandoning an `InputStream` without closing it** is a resource management bug: the network exchange may hold onto the connection and pooled resources. Therefore, you must read to EOF or close/cancel properly.

## 15. Debugging: why is the body missing or skipped?

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Status 200 but `Choice=SKIP_TYPE` | `Content-Type` not in allowlist | Inspect media type/charset; do not fake-fix the header |
| Status 200 but `Choice=SKIP_LENGTH` | `Content-Length` missing/large/malformed | Check chunked transfer and streaming option with hard cap |
| Status 404 with real body but `Choice.text()==""` | Handler decided `replacing` | Check `response.statusCode()` and decision, do not assume the server sent empty |
| 204 yet code expects body bytes | Violates no-content expectation | Check status and how the handler is used |
| Downloaded file contains HTML error content | Used `ofFile` without checking status/type | Use a custom handler selecting by metadata |
| `HttpResponse.body()` is null | Used `discarding()` (`Void`) | Use a typed result/`replacing` if you need to distinguish |
| Memory grows high despite checking `Content-Length` | Header is not a hard cap, high concurrency | Use bounded subscriber/stream + concurrency limit |
| `ofFile` download creates a partial file then fails | Transport/cancel/timeout | Clean up staging file according to ownership |
| `send` receives HTTP 500 without throwing | HTTP error status is still a response | Check status and business branch |
| `InputStream` keeps connection pool occupied | Not read to completion or closed | Try-with-resources / EOF |
| `sendAsync` callback stalls | Mapping/consumer doing heavy work | Offload blocking tasks from the client executor |
| File has a dangerous name | Trusted `Content-Disposition` from server | Use a controlled path, sanitize, and validate |

**Logging principle:** log `request method`, URI with query secrets stripped, status, `Content-Type`, `Content-Length` (if any), decision, actual bytes, and processing duration; **do not** log raw error pages, cookies, or `Authorization` headers.

## 16. Exercises with solutions

### Exercise 1 — Distinguish handler and subscriber

Has `BodyHandler.apply(info)` already received the response's `byte[]`?

**Answer:** Not yet. It receives **`ResponseInfo`** with status, headers, and version before the body is received/consumed; it must return a `BodySubscriber<T>` to process the body.

### Exercise 2 — Why does `BodyHandlers.ofString()` still receive a 404 body?

**Answer:** Built-in handlers generally **do not check the status code**; they receive the body using the `ofString` strategy. If you want to skip 404, write a custom `BodyHandler` that returns `BodySubscribers.replacing(...)` or `discarding()` on that branch.

### Exercise 3 — Wrong generic

A handler has type `BodyHandler<String>`, but the 404 branch returns `BodySubscribers.discarding()`. What is the issue?

**Answer:** `discarding()` returns `BodySubscriber<Void>`, which does not match `BodySubscriber<String>`. Use `replacing("")` or switch to `BodyHandler<Choice>` and map the branches.

### Exercise 4 — Small header, large body

The server declares `Content-Length: 100`, yet the application may receive beyond the limit due to corrupted data/encoding differences. Does checking `length <= 1024` already guarantee no more than 1024 bytes of memory are used?

**Answer:** No. The header is not a hard cap; you must count **actual bytes** and stop/cancel/close when exceeding the limit, along with a decompressed size limit if content encoding is used. Do not trust the header value as sufficient safety proof.

### Exercise 5 — Missing Content-Length

Response is 200, `Content-Type` is `text/plain`, but there is no `Content-Length`; must you discard the body?

**Answer:** No. The demo chose **fail-closed** and discarded it; production code can choose `ofInputStream()` and read at most `N+1` bytes then close, or use a custom `Flow` subscriber enforcing a hard cap.

### Exercise 6 — No body per HTTP semantics

The server returns `204 No Content`. Should you call `BodySubscribers.ofString` to parse JSON?

**Answer:** No. There is no content; return a typed `NO_BODY` result/`replacing` or `discarding`.

### Exercise 7 — 404 while downloading a file

A download endpoint returns 404 with an HTML body. What can using `BodyHandlers.ofFile(destination)` cause?

**Answer:** It can create the destination file containing the HTML error. Use a custom handler that checks status and media type **before choosing `ofFile`**, writes to an app-controlled path, and cleans up partial files on error.

### Exercise 8 — Bytes vs Java chars

A UTF-8 response contains Vietnamese diacritics; if you want a 64 KiB limit, is using `String.length()` after decoding the right approach?

**Answer:** No. You must limit the **actual received byte count** before accumulating into a `String`. `String.length()` counts UTF-16 code units, not the byte length on the wire.

### Exercise 9 — Useful error JSON

An API returns `422 application/problem+json` with error details. Must the response body be discarded?

**Answer:** No. If the application needs error details, choose a subscriber that saves/extracts a **bounded error record**, validates the schema, and does not log secrets. Do not retain errors of arbitrary length by default.

### Exercise 10 — InputStream lifecycle

After `BodySubscribers.ofInputStream()`, the caller reads the first 10 bytes and drops the stream object without closing it. What is the consequence?

**Answer:** It may hold onto the exchange's connection/resources; you must read to EOF or call `close()` to release them. Closing early may prevent the underlying connection from being reused.

### Exercise 11 — Redirect

Why should you inspect `response.uri()` / `previousResponse()` when downloading with redirects?

**Answer:** The final response may come from a **different origin** with different policy/trust. Checking only the final status/`Content-Type` without controlling redirects can download from an unwanted source.

### Exercise 12 — Range download

A `Range: bytes=1000-1999` request receives `206 Partial Content`. Can you overwrite the file starting from byte 0 as with a 200?

**Answer:** No. You must verify `Content-Range` and write at the exact offset; otherwise the file is corrupted. Status 206 requires a separate policy branch.

### Exercise 13 — Only need status/headers

A client wants to check the response status and `ETag`, without needing the body. What should it choose?

**Answer:** `BodyHandlers.discarding()` is the built-in option, or use a custom handler returning `BodySubscribers.replacing(...)` when you want a typed value representing the decision. Remember that discarding may still consume bytes over the network.

### Exercise 14 — sendAsync and memory

An application switches from `send` to `sendAsync` while still using `BodyHandlers.ofByteArray()` for 500 concurrent requests, each with a 20 MB response. Does the OOM risk disappear automatically?

**Answer:** No. `sendAsync` only changes how the result is awaited; each response still accumulates bytes. You need concurrency limits, hard byte sizes, streaming, and admission control.

## 17. Pre-deploy code review checklist

- [ ] I have identified which statuses and media types **are allowed to receive a body** according to the endpoint contract.
- [ ] I know `BodyHandler.apply(ResponseInfo)` runs **before** the body is consumed.
- [ ] Every custom handler branch returns the right `BodySubscriber<T>` with a unified generic type.
- [ ] I choose `replacing`/`discarding` for responses that do not need a body instead of `ofString()` by default.
- [ ] I distinguish 204/205/304/HEAD and no-content responses.
- [ ] I do not accept only status 200 if the API supports valid 201/202/206 responses.
- [ ] `Content-Type` is matched by appropriate media type/charset, not used as proof that data is safe.
- [ ] `Content-Length` is understood as **byte length**, optional/malformed, and not a hard barrier.
- [ ] For text/byte arrays, I enforce limits on **actually received bytes** and decoded size.
- [ ] For downloads, paths are controlled, using staging/`CREATE_NEW`, quota/checksum, and partial cleanup.
- [ ] For `ofInputStream`, always read to EOF or close in `try-with-resources`.
- [ ] For `ofPublisher`, there is a single subscriber and a clear lifecycle/cancellation.
- [ ] `mapping` does not perform long I/O/blocking work on the client executor.
- [ ] I check `statusCode()` and the decision before parsing the body or triggering side effects.
- [ ] When useful error bodies are needed, there is a separate branch with a hard cap and no secret logging.
- [ ] I have tests for 200 text, 200 binary, 204/304/HEAD, 404/500, oversized, no length, and malformed headers.
- [ ] I do not confuse discarding with “consuming zero network bandwidth”.
- [ ] I have controlled redirects, content-encoding, Range/206, cache/304, and timeouts as needed.
- [ ] I test with JDK 17+ in a controlled environment and do not rely on the Internet for unit tests.

## 18. Official documentation

- [Java SE 17 — HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): `apply(ResponseInfo)`, when status/headers are available, and creating a subscriber.
- [Java SE 17 — HttpResponse.ResponseInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.ResponseInfo.html): `statusCode()`, `headers()`, `version()`.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): built-in handlers and the key point that they **do not check status codes automatically**.
- [Java SE 17 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): `ofString`, `ofFile`, `ofInputStream`, `replacing`, `discarding`, `mapping`, Flow subscribers.
- [Java SE 17 — HttpResponse.BodySubscriber](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): `Flow.Subscriber<List<ByteBuffer>>`, `getBody()`, completion, and cancellation.
- [Java SE 17 — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html): `firstValue`, `firstValueAsLong`, case-insensitive names, and `NumberFormatException`.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, redirects/timeouts, HTTP versions.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): response status, headers, body, URI, and previous response.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): lightweight HTTP server used in both loopback examples.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): statuses 204, 205, 206, 304, HEAD, and response content semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): `Content-Length`, transfer framing, and message boundaries.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): `304 Not Modified` and cached representations.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): errors with `application/problem+json` representation.

**Conclusion:** `BodyHandlers.ofString()` is easy to use, but **does not automatically decide whether to receive the body based on status or media type**. Use a **custom `BodyHandler<T>`** to inspect `ResponseInfo` first, then return the **appropriate `BodySubscriber<T>`** — `replacing` when discarding, `ofString` for small text, `ofFile` for eligible downloads, `ofInputStream` for streaming. **`Content-Length` is only an early filter, not a hard limit**, and discarding does not mean blocking all bytes transmitted over the network. Good design requires getting **HTTP semantics, generic typing, resource cleanup, actual byte quotas, and error handling** all right.
