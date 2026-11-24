# Wrapping Requests/Responses to Read Content and Bound Memory in Spring MVC

> **Context:** Spring Web MVC using the Servlet API (`jakarta.servlet.*`) on Java 17+, such as Spring Boot 3.x / Spring Framework 6.x. This topic focuses on **`HttpServletRequestWrapper`, `HttpServletResponseWrapper`, `ContentCachingRequestWrapper`, and `ContentCachingResponseWrapper`**, reading HTTP bodies without breaking the processing flow, and **controlling how much memory is retained for logging/observation**. Clearly distinguish three limits: **cache size**, **accepted payload size**, and **memory across the entire pipeline (converters, file uploads, services)**.

## 1. Why Wrap Requests and Responses?

In the Servlet stack, HTTP bodies are read/written as streams. A Filter may want to measure or observe:

- Request method, URL, status, execution duration.
- A small preview of the request body when users call a JSON/text API.
- A small preview of the response body to diagnose errors in test environments.
- The number of response bytes written, enabling analysis of large responses without holding them all in RAM.
- Rejecting oversized uploads or JSON bodies with an independent limit policy.

The dangerous approach:

```java
// DO NOT use when the body can be very large.
byte[] all = request.getInputStream().readAllBytes();
System.out.println(new String(all, StandardCharsets.UTF_8));
chain.doFilter(request, response);
```

This illustrative code has two problems:

1. `readAllBytes()` can hold **the entire request body** on the heap. A request of several hundred MiB can cause GC pressure or `OutOfMemoryError`.
2. It **consumes the request input stream before** the controller and `HttpMessageConverter` read it; without a complete replay mechanism, `@RequestBody` afterward has no body left and may fail.

Responses have the same issue: buffering the body into an unbounded `ByteArrayOutputStream` for logging can force the server to keep multiple copies of a large file or JSON response.

**The right goal:** let the rest of the application read/write the body normally, retain at most a fixed number of bytes (e.g., **1024 bytes per direction/request**) for observation, and **do not mistake that number for a hard limit on the entire HTTP body**.

## 2. Servlet Wrapper Architecture

`HttpServletRequestWrapper` and `HttpServletResponseWrapper` belong to `jakarta.servlet.http` in Spring Boot 3.x. They implement the Decorator pattern: holding the real request/response, delegating methods to the underlying object by default, and allowing specific methods to be overridden.

```text
Client HTTP request
   |
Servlet Filter
   | new RequestWrapper(originalRequest)
   | new ResponseWrapper(originalResponse)
   |
   v
chain.doFilter(requestWrapper, responseWrapper)
   |
   v
DispatcherServlet
   |
Controller @RequestBody -> HttpMessageConverter reads wrapper.getInputStream()
   |
Controller returns DTO / String / Resource
   |
HttpMessageConverter -> wrapper.getOutputStream() / wrapper.getWriter()
   |
   v
Servlet container transmits bytes to client
   |
Filter logs bounded preview stats, status, duration (if sync)
```

Minimal structural example:

```java
class MyRequestWrapper extends HttpServletRequestWrapper {
    MyRequestWrapper(HttpServletRequest request) {
        super(request);
    }
}

class MyResponseWrapper extends HttpServletResponseWrapper {
    MyResponseWrapper(HttpServletResponse response) {
        super(response);
    }
}
```

This is a fragment describing the base classes, not a complete demo. A purely delegating wrapper will not cache the body on its own. To read or observe the body, use Spring's built-in wrappers or override stream reading/writing per Servlet rules.

**Do not arbitrarily mutate body bytes:** if a wrapper alters the body while keeping the old `Content-Length`, charset, `Content-Encoding`, or HMAC signature, downstream will misread it or fail signature verification. This article focuses primarily on **observation**, not mutating content.

## 3. Why Can a Request Body Normally Only Be Read Once?

`HttpServletRequest.getInputStream()` reads the HTTP entity body as bytes; `getReader()` reads via a `Reader` with character encoding. They are **mutually exclusive alternatives** and cannot be mixed arbitrarily on the same request under the Servlet contract.

In Spring MVC:

```java
@PostMapping(path = "/echo", consumes = MediaType.TEXT_PLAIN_VALUE)
@ResponseBody
String echo(@RequestBody String body) {
    return "echo:" + body;
}
```

This is an illustrative method: the message converter must read the body from the request stream to produce `String`. If a Filter already drained the stream, the converter cannot rewind it like a regular file.

### 3.1. Approaches

| Approach | Consumes Stream Before Handler? | Memory | When to Use? |
| --- | --- | --- | --- |
| Filter calls `readAllBytes()` before `doFilter` | **Yes** | Full body size, unsafe if uncapped | **Avoid** |
| `ContentCachingRequestWrapper(request, limit)` then downstream reads | Does **not** pre-read eagerly | Caches at most `limit` read bytes | Logging/observability of consumed requests |
| Build a replayable request from a bounded byte array | **Yes**, but wrapper serves stream from saved copy | Up to pre-set hard cap, plus copies if careless | Only when truly needing to pre-read and replay small bodies |
| Tee request stream, keeping a bounded prefix as downstream reads | Does **not** pre-read eagerly | Bounded to preview limit | Safe counting/sampling, advanced |
| Parse JSON/DTO in controller/service | Framework reads exactly once | Converter/object graph size | Business processing, not a substitute for an audit filter |

Key point: **the ability to inspect bytes that already passed through** and **the ability for downstream to re-read the same body** are two completely different capabilities.

## 4. ContentCachingRequestWrapper: Caches Only What Was Read

Spring provides:

```java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 1024);
chain.doFilter(wrapped, response);
byte[] preview = wrapped.getContentAsByteArray();
```

This is a fragment inside a Filter, not a standalone program. The converter/controller reads the body through `wrapped`; as it does, the wrapper copies **at most 1024 bytes** that were consumed. If the handler **does not read the body**, the cache can be **empty**. `getContentAsByteArray()` returns content **read up to the moment of the call**, without reading the whole request itself.

Per the Spring Framework 6.2 Javadoc, the constructor accepts `contentCacheLimit` to bound the cache; in recent Spring 6.2 patch lines, the no-limit constructor is even deprecated to encourage setting an explicit threshold. **Always use the constructor with a positive limit** for logging.

### 4.1. Cache Limit Is NOT an Upload Limit

Suppose an HTTP body is **10 MiB**, while the limit is **1024 bytes**. Once `@RequestBody` finishes reading, the converter can still receive and deserialize the full 10 MiB; `ContentCachingRequestWrapper` simply retains at most 1024 bytes in **the wrapper's cache**.

| Quantity | In This Example |
| --- | --- |
| Actual HTTP request body | 10 MiB |
| `contentCacheLimit` | 1024 bytes |
| `getContentAsByteArray().length` after downstream reads | At most 1024 bytes |
| Bytes converter is allowed to read | **Not blocked** by this cache setting |
| Heap limit for JSON tree/DTO | **Not guaranteed** by this cache setting |

The wrapper's default `handleContentOverflow(int limit)` does nothing. It **does not return 413 Payload Too Large by default** when the cache limit is exceeded. You can override the hook, but the exception occurs mid-stream-read and must be handled safely regarding filter/response commitment; do not treat overriding that hook as a complete upload-limiting policy.

### 4.2. Does ContentCachingRequestWrapper Allow Reading the Body a Second Time?

No. It provides an API to read **the cached copy** after the body has been consumed, rather than “rewinding” the entire input stream for `@RequestBody` to read again. Especially when the body exceeds `contentCacheLimit`, the cache does **not even hold the entire body**.

If a request truly must be re-read:

1. Pick a **finite hard cap** for the entire body.
2. Read at most `cap + 1` bytes (never `readAllBytes()`) before deciding to accept or reject.
3. Reject with **413 Content Too Large** if exceeded, including when the client omits `Content-Length`.
4. For valid bodies, build a custom `HttpServletRequestWrapper` returning a new `ServletInputStream` from the saved array; handle `getReader()`, encoding, and `isFinished`/`isReady`/`setReadListener` properly per the Servlet API.
5. For non-blocking/async/multipart, consider additional compatibility requirements; prefer container or codec-level mechanisms.

Pre-reading/replaying must always account for memory amplification across concurrent requests. If you only need logging, **do not replay**; bounded cache-on-read is simpler.

## 5. ContentCachingResponseWrapper: Convenient but Can Buffer the Entire Response

Spring provides `ContentCachingResponseWrapper`:

```java
ContentCachingResponseWrapper wrapped =
        new ContentCachingResponseWrapper(response);
try {
    chain.doFilter(request, wrapped);
    byte[] body = wrapped.getContentAsByteArray();
    // Use only when response is guaranteed small or strictly controlled.
} finally {
    wrapped.copyBodyToResponse();
}
```

This is a **simplified sync pattern**, not to be copied into production without size limits, async/error dispatch handling, or committed-state checks. Crucial points:

- `ContentCachingResponseWrapper` holds response bytes written through it in an internal buffer.
- `getContentAsByteArray()` returns a copy of **the cached response content**.
- You must call `copyBodyToResponse()` in typical sync usage to **flush the cached content to the original response**. Forgetting this call can leave the client with an empty or truncated body.
- Calling `flushBuffer()` on the wrapper **does not equate** to pushing the body to the original response before copying; understand the wrapper's behavior.
- The common API of this class **has no `(response, maxBytes)` constructor** to cap the total cache like the request wrapper.

For example, a 100 MiB response from `@ResponseBody` can make the wrapper hold ~100 MiB (aside from serializer/DTO/array copies) before copying to the client. If 100 such requests run concurrently, the cache alone reaches **~10 GiB** theoretically, excluding overhead. **Avoid wrapping entire responses with `ContentCachingResponseWrapper` on endpoints with large or unpredictable bodies.**

### 5.1. `copyBodyToResponse()` Does Not Guarantee Memory Safety

It solves **delivering the body to the client** after caching, not making caching itself bounded-memory streaming. This pattern fits intentional cases needing the whole response to compute an ETag or assert small test bodies. For instance, `ShallowEtagHeaderFilter` uses buffering to compute ETags, which carries a memory/latency trade-off.

### 5.2. Why Does Streaming Response Need Another Approach?

A large `Resource`/file endpoint, `StreamingResponseBody`, SSE, chunked transfer, or async rendering may need to push bytes continuously. Keeping the entire body on the heap defeats streaming, skews latency, and risks forgetting to flush/copy.

To **observe only a small prefix of the response**, use a **tee wrapper**: every byte written is forwarded immediately to the original Servlet output stream while also copying **at most the first N bytes** and counting total bytes passing through the wrapper.

## 6. Bounded Preview: Decoupling Observation from Body Size

A sound logging implementation:

```text
Controller writes byte[] / JSON / String
             |
             v
Response tee ServletOutputStream
     |
     +-----> original output stream -> client (writes everything)
     |
     +-----> preview buffer (at most 1024 bytes)
     |
     +-----> counter (bytes passed through)
```

For a **100 KiB** response with a 1024-byte preview:

- The client still receives the **full 100 KiB**.
- The tee wrapper retains **at most 1024 bytes**.
- The counter records how many bytes passed through the wrapper; no `byte[100KiB]` is allocated for logging.
- If the controller itself built a 100 KiB `String` or huge DTO, **controller/serializer memory** must still be managed separately. The bounded tee bounds only **the wrapper's extra memory**.

### 6.1. Important Note About `getWriter()`

A Servlet response has two writing modes:

- `getOutputStream()` for binary and converter output.
- `getWriter()` for character text with encoding.

A wrapper must handle **both**. On the same response, application code must not mix `getWriter()` and `getOutputStream()` as independent output modes; they are mutually exclusive per the Servlet contract. Overriding one while ignoring the other lets you log binary responses while missing HTML/text responses, or vice versa.

### 6.2. Preserving `isReady()` State and Write Listeners

`ServletOutputStream` has `isReady()` and `setWriteListener(...)` for non-blocking I/O. If a custom wrapper implements only `write(int)` and hardcodes `isReady()=true` regardless of the underlying stream, async code may write to a stream that is not ready or break the contract. Delegate readiness/listener APIs to the underlying stream. This **does not automatically make the wrapper fully async-aware**: the async lifecycle still requires dedicated design and testing.

### 6.3. What Data Should Be Retained?

The best default is **do not log raw bodies**. Even the first 1024 bytes can contain passwords, emails, bearer tokens, medical data, or secrets. Usually log metadata only:

```text
method=POST path=/api/echo status=200
request_cached_bytes=5
response_observed_bytes=10
response_preview_bytes=10
duration_ms=...
```

If body samples are genuinely needed for controlled debugging: allowlist endpoints/media types, redact before emitting logs, hide sensitive fields, skip multipart/binary, limit retention, and restrict log access. Hex/Base64 is **not** data masking; it merely changes representation.

## 7. Runnable Example: Bounded Request Cache + Bounded Response Tee

The following example uses **Spring Boot 3.x + Spring Web, Java 17+**, synchronous (synchronous request handlers). Each request retains **at most 1024 copied request bytes** and **1024 copied response bytes** at the observation layer. Responses are forwarded **directly** to the container instead of buffering everything before sending. No database, security, or AOP needed.

This demonstrates **memory bounding of an observability wrapper**, **not a hard HTTP payload limit**, and is **not optimized for async/SSE**. Demo endpoints intentionally use small bodies or a large String to show the difference.

### 7.1. Create the Project

From [Spring Initializr](https://start.spring.io/), choose Maven, Java 17+, Spring Boot 3.x, and the **Spring Web** dependency. Corresponding dependency section:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

This is a `pom.xml` fragment; the Initializr project provides the parent/BOM, Spring Boot plugin, and metadata. Put **all source** into a single file `src/main/java/com/example/demo/DemoApplication.java`. The file has only one public top-level class; the remaining package-private classes are valid in Java 17.

### 7.2. Full Java Code

```java
package com.example.demo;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletOutputStream;
import jakarta.servlet.WriteListener;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpServletResponseWrapper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Component
class BoundedBodyObservationFilter extends OncePerRequestFilter {

    private static final int PREVIEW_LIMIT = 1024;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI()
                .substring(request.getContextPath().length());
        return !path.startsWith("/api/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Cache only the request body portion that downstream actually reads.
        ContentCachingRequestWrapper req =
                new ContentCachingRequestWrapper(request, PREVIEW_LIMIT);

        // Avoid ContentCachingResponseWrapper because it can
        // keep the entire response body in RAM.
        BoundedResponseWrapper resp =
                new BoundedResponseWrapper(response, PREVIEW_LIMIT);

        long start = System.nanoTime();
        try {
            chain.doFilter(req, resp);
        } finally {
            // Demo only publishes final totals for sync requests.
            if (!req.isAsyncStarted()) {
                resp.flushObservedWriter();
                long elapsedNanos = System.nanoTime() - start;

                // Do not log raw request/response body.
                System.out.println(
                        "OBS " + req.getMethod() + " "
                        + req.getRequestURI()
                        + " status=" + resp.getStatus()
                        + " reqPreviewBytes="
                        + req.getContentAsByteArray().length
                        + " respPreviewBytes=" + resp.previewSize()
                        + " respObservedBytes=" + resp.observedBytes()
                        + " elapsedMs=" + elapsedNanos / 1_000_000L);
            } else {
                // With async: data may continue being written later.
                // Demo does not claim the byte count here is the final total.
                System.out.println("OBS async: completion not observed");
            }
        }
    }
}

class BoundedResponseWrapper extends HttpServletResponseWrapper {

    private final int limit;
    private final ByteArrayOutputStream preview;
    private long observed;

    private ServletOutputStream output;
    private PrintWriter writer;
    private boolean outputMode;
    private boolean writerMode;

    BoundedResponseWrapper(HttpServletResponse response, int limit) {
        super(response);
        if (limit < 1) {
            throw new IllegalArgumentException("limit must be positive");
        }
        this.limit = limit;
        this.preview = new ByteArrayOutputStream(limit);
    }

    private void remember(int oneByte) {
        observed++;
        if (preview.size() < limit) {
            preview.write(oneByte);
        }
    }

    private void remember(byte[] bytes, int off, int len) {
        observed += len;
        int canKeep = Math.min(limit - preview.size(), len);
        if (canKeep > 0) {
            preview.write(bytes, off, canKeep);
        }
    }

    // One stream shared between binary output and character writer.
    private ServletOutputStream outputDelegate() throws IOException {
        if (output == null) {
            ServletOutputStream target = super.getOutputStream();

            output = new ServletOutputStream() {

                @Override
                public boolean isReady() {
                    return target.isReady();
                }

                @Override
                public void setWriteListener(WriteListener listener) {
                    target.setWriteListener(listener);
                }

                @Override
                public void write(int b) throws IOException {
                    target.write(b);
                    remember(b);
                }

                @Override
                public void write(byte[] b, int off, int len)
                        throws IOException {

                    target.write(b, off, len);
                    remember(b, off, len);
                }

                @Override
                public void flush() throws IOException {
                    target.flush();
                }

                @Override
                public void close() throws IOException {
                    target.close();
                }
            };
        }
        return output;
    }

    @Override
    public ServletOutputStream getOutputStream() throws IOException {
        if (writerMode) {
            throw new IllegalStateException(
                    "getWriter() already selected");
        }
        outputMode = true;
        return outputDelegate();
    }

    @Override
    public PrintWriter getWriter() throws IOException {
        if (outputMode) {
            throw new IllegalStateException(
                    "getOutputStream() already selected");
        }
        writerMode = true;

        if (writer == null) {
            String encoding = getCharacterEncoding();
            Charset charset = encoding == null
                    ? StandardCharsets.ISO_8859_1
                    : Charset.forName(encoding);

            writer = new PrintWriter(
                    new OutputStreamWriter(outputDelegate(), charset));
        }
        return writer;
    }

    // Do not close the output stream; only flush the demo's sync writer.
    void flushObservedWriter() {
        if (writer != null) {
            writer.flush();
        }
    }

    int previewSize() {
        return preview.size();
    }

    long observedBytes() {
        return observed;
    }
}

@RestController
class DemoController {

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> echo(@RequestBody String body) {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/plain;charset=UTF-8"))
                .body("echo:" + body);
    }

    @GetMapping(
            path = "/api/large",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String large() {
        // Demo of a 10_000-byte ASCII String.
        // Do not build large Strings like this for file streaming.
        return "x".repeat(10_000);
    }

    @GetMapping("/api/writer")
    public void writer(HttpServletResponse response)
            throws IOException {

        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("hello writer");
    }
}
```

**Design QA on the source code:**

- `ContentCachingRequestWrapper(request, 1024)` sets a **1024-byte max request cache**; the wrapper does not eagerly pre-read the body.
- `BoundedResponseWrapper` retains **at most a 1024-byte prefix** while using `observed` to count bytes written through the wrapper. `ByteArrayOutputStream(limit)` is capped by `remember(...)` logic and does not grow with response size.
- `outputDelegate()` delegates `write(...)` to the underlying stream **before** appending to the preview. The response never waits to accumulate the whole body into an array.
- `getWriter()` uses the same output delegate and resolved encoding; `getOutputStream()` / `getWriter()` are mutually exclusive.
- `writer.flush()` in `finally` on the **sync demo path** ensures content buffered by the writer reaches the underlying stream. Real apps must respect full flush/commit/reset lifecycles, async callbacks, error dispatches, and wrapper nesting.
- `setWriteListener`/`isReady` delegate to the underlying stream, though this code **is not designed for full async stream observation**; when a request switches to async, the filter explicitly logs that completion was not observed.
- Responses generated by `sendError()`/`sendRedirect()` or the servlet container itself can **bypass `write()` calls observed by the wrapper**; the counter is not the exact “on-the-wire” byte count after HTTP compression/chunking/TLS.
- `@RequestBody String` can still allocate memory proportional to body size inside the MVC converter. **The 1024-byte Filter limit does not constrain this `String`'s size.**
- The example prints metadata only, never the raw payload. In production, avoid logging paths containing PII/tokens; redact query strings and headers.

### 7.3. Running the Application

At the Spring Initializr project root:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
```

Spring Boot uses `http://localhost:8080` by default unless `server.port`/context path is changed.

### 7.4. HTTP Test: Small Text Request

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
```

Relevant response:

```http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

echo:hello
```

Console prints a line like:

```text
OBS POST /api/echo status=200 reqPreviewBytes=5 respPreviewBytes=10 respObservedBytes=10 elapsedMs=...
```

Explanation:
- Input `hello` is 5 ASCII bytes.
- Output `echo:hello` is 10 ASCII bytes.
- The 1024 preview limit is not reached, so cached/observed byte counts match actual sizes in this demo.
- `elapsedMs` depends on hardware/server/GC and has no fixed value.

### 7.5. HTTP Test: Response Larger Than Preview Limit

```bash
curl -sS -o large.txt http://localhost:8080/api/large
wc -c large.txt
```

On Unix with `wc`, stdout:

```text
10000 large.txt
```

Console prints a line like:

```text
OBS GET /api/large status=200 reqPreviewBytes=0 respPreviewBytes=1024 respObservedBytes=10000 elapsedMs=...
```

This is the key contrast: the client receives all **10,000 bytes**, yet the wrapper stores only **the first 1024 bytes** in its observation buffer. `reqPreviewBytes=0` because the GET endpoint reads no request body. If OS/tools display extra metadata, only the file's byte count needs to be checked.

### 7.6. HTTP Test: Writing via getWriter()

```bash
curl -i http://localhost:8080/api/writer
```

Body:

```text
hello writer
```

Server log line like:

```text
OBS GET /api/writer status=200 reqPreviewBytes=0 respPreviewBytes=12 respObservedBytes=12 elapsedMs=...
```

The string `hello writer` is **12 ASCII bytes**. This test catches wrappers that override `getOutputStream()` while forgetting `getWriter()`.

### 7.7. cURL Commands on Windows PowerShell

Bash uses `\` for line continuation; PowerShell uses different syntax. Run a single-line command with `curl.exe`:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/echo" -H "Content-Type: text/plain" --data-binary "hello"
```

To verify the large file on Windows, you can use PowerShell:

```powershell
curl.exe -sS -o large.txt http://localhost:8080/api/large
(Get-Item large.txt).Length
```

The displayed value is `10000`.

## 8. Observation Memory Limit ≠ HTTP Request Size Limit

At least four resource layers can grow with user input:

```text
Client payload
   |
Reverse proxy / ingress (body size / timeout / rate limits)
   |
Servlet container (multipart/form limits, buffers, connection policy)
   |
Filters (bounded preview vs full caching)
   |
MVC converters (JSON object graph, String @RequestBody, byte[] payload)
   |
Controller / service (lists, files, temp objects, database transactions)
```

**Example:** the filter keeps at most 1024 bytes, yet the controller accepts `@RequestBody byte[]` with a 200 MiB body. The converter can still allocate a ~200 MiB byte array, plus copies/overhead. Hence, hard payload policies must be enforced **before or during body consumption**, not merely in a logging filter.

### 8.1. Content-Length Is Only a Fast Check, Not Sufficient

```java
long length = request.getContentLengthLong();
if (length > MAX_ALLOWED_BYTES) {
    response.sendError(413, "Content Too Large");
    return;
}
```

This is an early-check snippet inside a Filter, **not a complete hard-cap mechanism**:
- `Content-Length` may be absent or `-1`, especially with chunked encoding.
- Actual body size after transfer decoding/compression can differ from the header number.
- Proxy/container layers may have their own rules before the filter.

To enforce a **hard cap** for generic JSON/binary requests, count **actual bytes read from the input stream** via a bounded/counting decorator or an equivalent proxy/container policy. Once exceeded, stop reading and return 413 while the response can still be written; handle exception propagation, the HTTP connection, and response commit state properly. Test requests with and without `Content-Length`, slow uploads, chunked transfers, and concurrent requests. If writing a custom `ServletInputStream` decorator, preserve non-blocking semantics.

### 8.2. Bounded Read Pattern Before Building a Replay Buffer

In a **synchronous** environment with a small hard cap, if you genuinely must pre-read and replay, avoid:

```java
// Never use with unbounded input!
byte[] body = request.getInputStream().readAllBytes();
```

Use a bounded read pattern:

```java
// Pseudocode illustrating the decision, NOT a complete filter.
int limitBytes = 1024 * 1024;
byte[] data = request.getInputStream()
        .readNBytes(limitBytes + 1);

if (data.length > limitBytes) {
    // Return 413 before allowing further processing.
    // Do not call chain.doFilter with an already-consumed stream.
} else {
    // Only wrap the request in a true replayable wrapper if needed.
    // The wrapper must fully implement getInputStream/getReader.
}
```

`readNBytes(limit+1)` retains a bounded amount of data, detecting oversized bodies without loading the whole payload. However, it **has already consumed the stream**, so a proper replay wrapper is needed for downstream to read valid bytes. For bodies exceeding the limit, container connection close/drain policies may be needed; never assume subsequent requests on the same keep-alive connection always work normally after aborting mid-stream.

### 8.3. Multipart Upload and HTTP Form Configuration

Spring Boot 3.x supports distinct properties for different body-reading paths:

```properties
# Multipart (file upload); example application policy:
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
spring.servlet.multipart.file-size-threshold=0B

# Form POST limit handled by embedded Tomcat:
server.tomcat.max-http-form-post-size=2MB
```

Meaning:
- `max-file-size` limits a single file within a multipart request.
- `max-request-size` limits the total multipart request.
- `file-size-threshold=0B` means multipart config can spill file contents to disk per Servlet multipart mechanics; this does **not** eliminate disk exhaustion or the need to manage temp files/cleanup.
- `server.tomcat.max-http-form-post-size` applies to form POSTs parsed by Tomcat, **not** as a universal hard limit for all `application/json`/binary requests.

These properties vary by Servlet container (Tomcat/Jetty/Undertow), Spring Boot version, and parser framework. Check [Spring Boot Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) and integration-test your application's actual payload types.

### 8.4. Large Uploads: Stream Instead of Holding byte[]

With `MultipartFile`, avoid:

```java
byte[] all = file.getBytes(); // can allocate a huge array in RAM
```

When saving files by design, use `file.getInputStream()` and copy **using a small buffer** to controlled storage, or `file.transferTo(...)` where appropriate. You still need:
- hard file/request size limits;
- quotas on disk space, upload count, part count, and processing time;
- MIME sniffing/format validation without trusting client-supplied filenames/`Content-Type` blindly;
- appropriate scanning/sandboxing when processing untrusted content;
- permission checks, path traversal protection, and temporary file cleanup.

`MultipartFile` may already have been processed by the Servlet multipart resolver/container before the controller runs; placing a filter after the parser does not automatically make that phase bounded-memory. Inspect filter order and multipart infrastructure if measuring parts of the body.

## 9. Comparing ContentCaching Wrappers and Tee Wrappers

| Scenario | ContentCachingRequestWrapper | ContentCachingResponseWrapper | Bounded Tee Wrapper |
| --- | --- | --- | --- |
| Observing request body already read by handler | Great fit with a positive cache limit | Not applicable | Custom request tee also works |
| Allowing converter to re-read request | **Not automatically** | Not applicable | Only if building a dedicated replay wrapper |
| Buffering entire response to compute hash/ETag | No | Yes, with memory trade-off | No if only keeping a prefix |
| Observing very large responses | Not applicable | Risk of buffering full body | **Prefer bounded tee**, or skip body logging |
| Capping allowed request body upload size | No, only caps cache | No | Preview tee does **not** either; need counting hard limit |
| Modifying body once read? | Not easy; needs replay/custom | Possible on full buffer in sync, though complex | Not intended to modify body |
| Must copy body back to response? | No `copyBodyToResponse()` | **Yes** in buffering wrapper pattern | No, tee forwards immediately |
| Async/SSE/non-blocking | Must understand dispatch/stream lifecycle | Easily breaks streaming | Must be designed as explicitly async-aware |

**There is no universal wrapper that “re-reads any body, uses zero RAM, streams, mutates content, and auto-returns 413.”** Each requirement carries its own trade-offs; build the least-privileged, simplest wrapper that fits your need.

## 10. Reading Bodies for Logging Can Cause Content Bugs and Security Leaks

### 10.1. Do Not Arbitrarily Decode Binary as Text

An `application/octet-stream`, JPEG image, zip, PDF, or compressed response cannot simply be decoded with `new String(bytes, UTF_8)` and expected to yield meaningful text. A byte prefix can also slice right through a multi-byte UTF-8 character, producing replacement characters `�` in the preview string.

For diagnostics:
- Prefer logging byte count, media type, status, and sanitized paths.
- Render a text preview only if the media type is allowlisted and the charset is verified.
- For JSON, use schema-based redaction; regex scrubbing of sensitive fields on a truncated JSON substring is **unreliable** when cut mid-field or mid-escape.
- Hex or Base64 merely changes encoding; it does **not** mask sensitive data.

### 10.2. Authorization and Sensitive Data

A filter may run before authentication completes, so logging raw request headers/bodies can capture cookies, bearer tokens, passwords, API keys, and sensitive data. On 401/403 errors, redaction policies are even more critical. Never store bodies for login/payment/health-record endpoints just for easier debugging.

If using Spring Security:
- Review filter order and `SecurityFilterChain`.
- Avoid logging raw principals/headers from untrusted sources.
- Use secret-free correlation IDs instead of dumping payloads.
- Verify log retention, encryption at rest, access control, and which environments enable sampling.

### 10.3. Compression, Transforms, and Bytes-on-Wire

A response wrapper counts bytes written through the wrapper itself. If an outer filter/container applies gzip/Brotli compression, HTTP chunked encoding, TLS encryption, or proxy transforms, bytes on the network can **differ**. Do not treat a tee wrapper's counter as exact wire-level bytes without knowing its filter-chain position and transfer encoding.

Additionally, `HEAD`/`304 Not Modified` responses have no body per HTTP semantics. A wrapper writing headers/bodies improperly can break those conditions. For HTTP caching/ETags/streaming, consider the framework's built-in capabilities.

## 11. Async, Error Dispatches, and Response Lifecycle

### 11.1. OncePerRequestFilter Does Not Guarantee Once Across an Entire Async Lifecycle

`OncePerRequestFilter` supports filtering per Servlet request dispatch with hooks such as:
- `shouldNotFilter(HttpServletRequest)`.
- `shouldNotFilterAsyncDispatch()`.
- `shouldNotFilterErrorDispatch()`.

With `Callable`, `DeferredResult`, `StreamingResponseBody`, or SSE, a request can switch to async and the response can continue being written **after the initial `chain.doFilter()` returns**. Therefore, code like:

```java
chain.doFilter(requestWrapper, responseWrapper);
log(responseWrapper.getContentAsByteArray());
```

may observe an **incomplete body** or conflict with the async lifecycle. The demo in Section 7 intentionally logs final totals only for synchronous handlers.

If production async support is required:
1. Register wrappers/filters with the proper dispatcher types.
2. Consider `AsyncListener` (`onComplete`, `onError`, `onTimeout`, `onStartAsync`), or an equivalent tracing layer, to capture true completion.
3. Do not flush/close Servlet streams on the wrong thread or at the wrong moment.
4. Keep previews bounded and thread-safe under concurrent callbacks.
5. Test async, errors, cancellations, timeouts, and nested wrappers.
6. Never use `ThreadLocal`/MDC across async threads without propagation/cleanup.

### 11.2. Error Dispatches and sendError

Exceptions occurring in a Filter **before `DispatcherServlet`** are not caught by `@RestControllerAdvice` by default. The Servlet container may initiate an ERROR dispatch to the error controller; the filter can run again if registered for `DispatcherType.ERROR`. Container-handled `sendError(...)`/`sendRedirect(...)` calls also do not necessarily go through the wrapper's `ServletOutputStream.write(...)`.

Thus previews/counts reflect **observations within the wrapper's scope**, not the entire raw HTTP response produced by container error pages and the network stack.

### 11.3. Flush, Committed Status, and Content-Length

Once a response is committed, you cannot arbitrarily reset the body or change status/headers. With a pass-through (tee) wrapper writing straight to the container, you cannot rewind and edit already-sent bytes. To alter JSON output, use `ResponseBodyAdvice` or a custom `HttpMessageConverter` within controlled bounds; to rewrite an entire HTML/file body, you must accept bounded buffering or complex streaming transformations.

Never set `Content-Length` using a Java String's **character** count: HTTP length is measured in **bytes** per the encoding. For UTF-8 text responses containing Vietnamese characters, `String.length()` usually differs from the actual byte count.

## 12. Resources and Memory in a Real Server

Suppose each request keeps a 1 KiB preview per direction (excluding wrapper objects/metadata):
- 1 request: at most **2 KiB of preview data**.
- 1,000 concurrent in-flight requests: at most roughly **2 MiB of preview content**.
- If buffering an entire 10 MiB response/request in `ContentCachingResponseWrapper`, 1,000 requests could require roughly **10 GiB** for cached bodies alone, excluding copies, serializers, object graphs, container buffers, and JVM overhead.

These are **raw data capacity** estimates, not exact heap measurements. `ByteArrayOutputStream` has initial capacity, overhead, and array allocations; `getContentAsByteArray()` can allocate copies; logging formatters/queues can retain additional data. Under high concurrency, shrinking previews, sampling, and managing other buffers helps more than micro-optimizing one class.

Limits to budget together:
- **Request concurrency:** thread pools, queues, and open connections.
- **Request bodies:** proxy/container/codec/parser hard caps and read timeouts.
- **Output generation:** avoid building huge Strings/`byte[]`; use streaming/resources where appropriate.
- **Uploads:** multipart thresholds, disk quotas, cleanup, and antivirus scanning.
- **Logs:** batch/async appender queues, message truncation, sampling, and retention.
- **Heap:** leave sufficient headroom for GC, converter object graphs, caches, HTTP sessions, and service data.

## 13. Common Pitfalls

| Symptom | Reason | Fix |
| --- | --- | --- |
| `@RequestBody` is empty after logging Filter | Filter drained the stream first | Use cache-on-read only or a hard-capped replay wrapper |
| Request cache is empty despite body sent | Downstream never consumed the body or wrapper placed wrongly | Cache reflects **bytes read**, does not pre-read |
| Oversized request still reaches controller | `contentCacheLimit` only bounds the cache | Enforce hard body size at ingress/container/counting layer |
| Client gets empty response with caching wrapper | Forgot `copyBodyToResponse()` | Copy body in proper sync lifecycle or choose a tee |
| Large response triggers OOM | `ContentCachingResponseWrapper` buffers full body | Bounded tee/no body logging, streaming output |
| Captures binary writes but misses text | Wrapper overrode only `getOutputStream()` | Support `getWriter()` as well with proper charset |
| Servlet rejects calling `getWriter/getOutputStream` | Mixing both modes | Respect mode exclusivity |
| UTF-8 preview contains garbled chars | Byte slice cut mid-code-point | Log metadata only or decode complete characters safely |
| `postHandle` cannot read response body | Body already sent by converter | Use a response wrapper in Filter or `ResponseBodyAdvice` |
| Response has wrong `Content-Length` | Added/removed bytes after length was set | Let container/converter manage it, or recompute exact byte count |
| Async response log missing final totals | Filter returned before async completion | `AsyncListener`/proper async-aware design |
| Body logs leak tokens/passwords | Missing allowlist/redaction | Metadata-only, allowlists, log protection |
| Logging 1 MiB/request spikes heap | Preview limit too large under high concurrency | Cap to a few KiB, use sampling |
| Filter runs twice | Double registration / ERROR dispatch | Check mappings/order and `OncePerRequestFilter` |
| 413 never triggers on chunked requests | Trusting `Content-Length` alone | Count actual bytes, enforce at proxy/container |
| Logged byte count mismatches `Content-Length` | Compression/transfer coding/partial content | Account for wrapper position and wire encoding |

## 14. Review Checklist for Request/Response Wrapping

1. Is the goal **observation**, **body transformation**, or **payload limit enforcement**? Are those responsibilities separated?
2. Does it retain **at most N bytes** per request/response, rather than calling `readAllBytes()` or buffering the entire response?
3. Were `getReader()` or `getWriter()` overlooked?
4. If using `ContentCachingRequestWrapper`, is it clear the cache holds only bytes read downstream and **does not allow replaying the full body**?
5. If using `ContentCachingResponseWrapper`, are `copyBodyToResponse()` and full-buffering risks controlled?
6. If using a custom tee, are all key write/flush/ready/listener operations delegated and writer encodings handled properly?
7. For async/error dispatches, does the wrapper have an explicit lifecycle and tests for timeout/error/completion?
8. Are data redaction, access auditing, sampling, sampling limits, retention, and log queue limits in place?
9. Are hard body limits based on **actual bytes** and do they handle missing `Content-Length`?
10. Are multipart uploads/file streaming handled separately?
11. Does the memory budget account simultaneously for converter bodies, object graphs, temp files, copies, and concurrent requests?
12. Do tests verify the client receives the **complete body** even when only a short preview is cached?

## 15. Self-Check

**Question 1.** Does `ContentCachingRequestWrapper(req, 1024)` automatically return HTTP 413 if a request body is 5 MiB?

**Answer:** No. That limit caps the **cache**; it does not stop downstream from reading the body. An independent hard body limit is required.

**Question 2.** Why should a Filter not call `request.getInputStream().readAllBytes()` to log and then continue `chain.doFilter`?

**Answer:** It risks loading the entire body onto the heap and consumes the stream needed by `@RequestBody`. If pre-reading is required, use a hard cap and a real replay wrapper; for observation only, use cache-on-read/tee.

**Question 3.** With `ContentCachingResponseWrapper`, why must `copyBodyToResponse()` be called?

**Answer:** It buffers the response body internally; cached bytes must be copied to the original response in standard sync lifecycles so the client receives the content.

**Question 4.** If an app serves a 50 MiB file and only wants to count bytes + retain the first 1 KiB, should it use `ContentCachingResponseWrapper`?

**Answer:** Not ideal; it could hold the entire file in RAM. Use a bounded tee or skip body logging, and choose proper streaming/resource handling.

**Question 5.** A request sends `Transfer-Encoding: chunked` without `Content-Length`. Does checking `getContentLengthLong()` enforce a hard limit?

**Answer:** No. A proxy/container policy or counting actual bytes read is needed, including when the length header is absent.

**Question 6.** Why can body previews still leak secrets even when capped at 1024 bytes?

**Answer:** Passwords, tokens, emails, or private fields can appear right at the beginning of the body. Default to metadata-only logging; body sampling requires allowlists/redaction/retention/access control.

**Question 7.** When an async response keeps writing after `chain.doFilter()` returns, is a byte count logged inside the Filter complete?

**Answer:** Not guaranteed. An async-aware lifecycle and completion callbacks are required to finalize metrics.

## 16. Official References

- [Spring Framework 6.2 — ContentCachingRequestWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html): cache limit, caching only read bytes, and `handleContentOverflow`.
- [Spring Framework 6.2 — ContentCachingResponseWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/ContentCachingResponseWrapper.html): caching response body, `getContentAsByteArray()`, `copyBodyToResponse()`.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): Filter, `OncePerRequestFilter`, async/error dispatches.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.servlet.multipart.*`, Tomcat form limits, and container limits.
- [Spring Boot 3.5 — MultipartProperties Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html): file/request sizes and thresholds.
- [Jakarta Servlet API — HttpServletRequestWrapper](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequestwrapper): delegating/overriding request behavior.
- [Jakarta Servlet API — HttpServletResponseWrapper](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletresponsewrapper): delegating/overriding response behavior.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): how bodies flow from Servlet input stream to controller arguments and from return values to output stream.

**Conclusion:** for request observation, `ContentCachingRequestWrapper` with a positive limit is a solid choice when you only need bytes downstream has read. For observing large responses, avoid using `ContentCachingResponseWrapper` as a default logger because it can buffer the entire body; use a **bounded streaming tee** or log metadata only. No preview limit **replaces a hard HTTP payload limit**, converter/service memory policies, upload controls, async lifecycle handling, or log security.
