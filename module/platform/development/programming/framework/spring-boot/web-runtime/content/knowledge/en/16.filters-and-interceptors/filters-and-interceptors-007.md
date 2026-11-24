# ContentCachingRequestWrapper, ContentCachingResponseWrapper, and Usage Limits in Spring Boot

When writing servlet filters, learners often want to **read the HTTP request and response bodies** for auditing, measuring size, debugging traces, or computing checksums. The Servlet API does not allow every middleware to read bodies arbitrarily many times: the request input stream is normally consumed sequentially as a stream, and the response output stream is where the server writes outgoing data. Spring Framework provides two helpful wrappers:

- **ContentCachingRequestWrapper**: retains a copy of the request bytes **that were actually read downstream**. Afterward, that copy can be retrieved with `getContentAsByteArray()` or `getContentAsString()`.
- **ContentCachingResponseWrapper**: buffers the bytes written by downstream into the response wrapper, letting you inspect a copy, and then **requires calling `copyBodyToResponse()`** to transfer the content to the underlying response.

Both classes live in **org.springframework.web.util** and belong to the **Servlet stack**, used with **jakarta.servlet.http.HttpServletRequest/HttpServletResponse** in Spring Boot 3.x. They are **not** equivalents for a server running purely on Spring WebFlux + Reactor Netty.

This lesson explains the actual mechanism, key limitations, a runnable Maven example on Spring Boot 3.5.x + Java 17+, MockMvc tests, and cases where body buffering should not be used.

## 1. Quick Comparison Table

| Question | ContentCachingRequestWrapper | ContentCachingResponseWrapper |
|---|---|---|
| What does it wrap? | HttpServletRequest | HttpServletResponse |
| When is the cache populated? | When downstream reads the input stream/reader or eligible parameter reads | When downstream writes to the wrapper's output stream/writer |
| Does it automatically read the body on construction? | **No** | No; it only intercepts data written through the wrapper |
| How do you read the cache? | getContentAsByteArray(), getContentAsString() | getContentAsByteArray(), getContentInputStream(), getContentSize() |
| Does the constructor cap cache size? | Has an overload taking contentCacheLimit | No corresponding limit overload in the Spring Framework 6.2 API |
| What if nothing reads/writes? | Cache can be empty | Cache has no data |
| Must the body be copied back? | **No** | **Yes**, call copyBodyToResponse() at the right time |
| Does it make the request body replayable? | **No**; it only holds a copy of what was consumed | Not applicable to request input |
| Biggest pitfalls | Reading too early, misinterpreting cache limit, logging sensitive data | Forgetting to copy, buffering large responses, streaming/async, error dispatches |
| Where is it used? | Servlet filter/Servlet MVC HTTP request | Servlet filter/Servlet MVC HTTP response |

**Short takeaway:** The request wrapper **observes what has been read**; the response wrapper **buffers what has been written and must forward it**. They do not share the same lifecycle and cannot be used interchangeably.

## 2. Servlet Filters, DispatcherServlet, and When the Body Can Be Observed

In Spring Boot with spring-boot-starter-web:

~~~text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty/Undertow depending on configuration)
    |
    v
Servlet Filter chain
    |
    +-- ContentCachingRequestWrapper(request)
    +-- ContentCachingResponseWrapper(response)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping / Controller
    |       |
    |       +-- @RequestBody read by HttpMessageConverter
    |       +-- Response DTO serialized via HttpMessageConverter
    |
    v
Filter resumes after chain.doFilter(...)
    |
    +-- requestWrapper.getContentAsByteArray()
    +-- responseWrapper.getContentAsByteArray()
    +-- responseWrapper.copyBodyToResponse()
    |
    v
Client receives response body
~~~

From the filter's perspective:

- Code **before** `filterChain.doFilter(...)` runs before the controller and converters process the body.
- Code **after** `filterChain.doFilter(...)` runs once synchronous downstream work completes.
- The request cache fills **while** the controller/converter consumes the request body.
- The response cache fills **while** the controller/converter writes the response body into the wrapper.
- The filter must copy the response body back to the underlying response at the proper lifecycle point.

This diagram applies to **synchronous processing**. If a request initiates Servlet async or streaming, `chain.doFilter()` can return **before the response is complete**. Never blindly apply the sync pattern there.

## 3. ContentCachingRequestWrapper: Caches Only Consumed Bytes

Spring Framework 6.2 API:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 1024);

byte[] cachedBytes = wrapped.getContentAsByteArray();
String cachedText = wrapped.getContentAsString();
~~~

This snippet only illustrates the API; it requires an `HttpServletRequest` variable `request` and importing `org.springframework.web.util.ContentCachingRequestWrapper`.

**Important:** right after construction, `cachedBytes` can be an empty array even when the HTTP request carries a real body. The wrapper **does not proactively read the input stream**. It only records bytes as a downstream component calls `getInputStream()`/`getReader()` and actually reads data.

Example:

~~~text
POST /api/demo/echo
Content-Type: text/plain

hello

T0: Filter constructs ContentCachingRequestWrapper
    cache = [] (0 bytes)

T1: Filter calls filterChain.doFilter(wrapper, response)
    @RequestBody String reads 5 bytes from ServletInputStream
    cache = "hello" (5 bytes)

T2: Filter resumes after chain.doFilter
    getContentAsByteArray() = 5 bytes
~~~

If an endpoint does not read a request body (such as `GET /ping`), the request cache remains 0 bytes. That is **correct behavior**, not a broken wrapper.

### 3.1. Reading the Cache Before the Chain Has No Effect

Wrong expectation:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 1024);

log.info("body={}", wrapped.getContentAsString());
filterChain.doFilter(wrapped, response);
~~~

The log line prints an empty string because nothing has read the body yet. To observe bytes processed by the controller, **read the cached content after downstream finishes**.

### 3.2. Never Read the InputStream in the Filter Before the Controller

Some code tries to "fill the cache" using:

~~~java
byte[] bytes = wrapped.getInputStream().readAllBytes();
filterChain.doFilter(wrapped, response);
~~~

This is an **anti-pattern**. Reading the InputStream consumes the request body, leaving downstream `@RequestBody` with EOF or missing bytes. `ContentCachingRequestWrapper` keeps a copy of what was read, but **does not rewind the InputStream for the controller to read again from the beginning**.

If a real requirement demands reading the body multiple times, build a dedicated design with size bounds and a proper replayable input wrapper. Never treat `ContentCachingRequestWrapper` as a complete "re-readable request wrapper."

### 3.3. getContentAsByteArray and getContentAsString

- `getContentAsByteArray()`: returns a `byte[]` containing the cached portion.
- `getContentAsString()`: decodes the cached portion using the wrapper's configured charset, available since Spring Framework 6.1.
- Byte length does not equal Unicode character count: a multi-byte character (such as Vietnamese text or emojis) can occupy multiple UTF-8 bytes.
- If the body is JSON and you need its structure, deserialize with a proper JSON parser after enforcing privacy controls; avoid arbitrary `substring` calls on raw bodies.
- If Content-Type is multipart, octet-stream, or a file upload, never convert raw `byte[]` directly to String and log it.

In middleware that only measures payload size, **`cache.length`** is sufficient. Never log body contents by default.

## 4. What contentCacheLimit Protects Against — and What It Does Not

The constructor:

~~~java
new ContentCachingRequestWrapper(request, 1024);
~~~

instructs the wrapper to retain **at most 1,024 bytes of the request body copy**. It **does not**:

- reject HTTP requests larger than 1,024 bytes;
- restrict the controller to reading only 1,024 bytes;
- truncate the payload delivered to the business handler;
- guarantee the entire body was cached;
- replace upload, JSON parser, proxy, or servlet container size limits;
- provide an absolute safety cap on total memory used by the application.

If a client sends **2,048 ASCII characters** and the controller reads all of them, the controller still receives all 2,048 characters, while the wrapper only caches the first 1,024 bytes.

~~~text
Wire request body:                2048 bytes ASCII
Request cache copy limit:         1024 bytes
Controller @RequestBody reads:    2048 bytes
getContentAsByteArray():          1024 bytes
Conclusion: only the OBSERVATION copy is capped
~~~

### 4.1. handleContentOverflow

Spring Framework provides a hook:

~~~java
protected void handleContentOverflow(int contentCacheLimit)
~~~

Its default implementation does nothing. When bytes read exceed the limit, a subclass **can** override this hook to react accordingly.

However, do not assume overriding the hook to throw an exception is a universally safe production upload-limit mechanism across all flows: you must understand when the body is read, how the container handles the request, how exceptions are mapped, and how streaming/multipart behaves. To enforce real request size limits, configure limits at the gateway, container, codec, endpoint, or service level as appropriate.

### 4.2. Reaching the Exact Limit Does Not Prove Overflow

If `cache.length == 1024`, there are two possibilities: either **exactly 1,024 bytes** were read, or the body was **larger** and the cache capped it. Never attach a `"TRUNCATED"` label solely because `cache.length == limit`. If you need an exact overflow flag, use the overflow hook/metrics per specification and test with payloads exceeding the threshold.

## 5. ContentCachingResponseWrapper: Buffered Response Must Be Flushed Back

Unlike the request wrapper, the response wrapper intercepts data **written out by downstream**:

~~~java
ContentCachingResponseWrapper wrapped =
        new ContentCachingResponseWrapper(response);

filterChain.doFilter(request, wrapped);

byte[] cachedResponse = wrapped.getContentAsByteArray();
wrapped.copyBodyToResponse();
~~~

This snippet is a **pattern for a successful synchronous flow**. Production code must ensure copying in `finally` and handle async/errors separately.

When the controller writes to the wrapper's writer/output stream, bytes are stored inside the wrapper instead of being sent immediately to the underlying `HttpServletResponse`. After measuring, logging redacted metadata, or computing a hash, you must call:

~~~java
wrapped.copyBodyToResponse();
~~~

to transfer the content to the real response. If forgotten, the HTTP client can receive an **empty** or incomplete body even though the controller generated the response properly.

### 5.1. flushBuffer Does Not Replace copyBodyToResponse

The Javadoc for `ContentCachingResponseWrapper` notes that **`flushBuffer()` does not flush the cached content to the client or commit the underlying response** while the body still resides in the wrapper. To copy the entire cached body, call `copyBodyToResponse()`.

Do not write:

~~~java
wrapped.flushBuffer();  // Does NOT replace copyBodyToResponse()
~~~

and assume the client has definitely received the full response.

### 5.2. Do Not Call copyBodyToResponse Too Early

If you copy the body while the controller or a downstream filter **is still writing**, the application can suffer missing data, mismatched Content-Length, duplicates, or corrupted streams. Know clearly when synchronous response generation finishes. The `finally` sync pattern in the demo is valid only because endpoints are bounded to small synchronous bodies.

### 5.3. Response Wrapper Has No Corresponding contentCacheLimit

In Spring Framework 6.2, `ContentCachingResponseWrapper` wraps an `HttpServletResponse` and **has no public constructor with a `contentCacheLimit` equivalent to the request wrapper**.

This matters because:

- multi-megabyte responses can be buffered in memory;
- calling `getContentAsByteArray` allocates another `byte[]` for inspection;
- concurrent requests multiply memory consumption;
- streaming responses can get stalled instead of arriving incrementally at the client;
- caching can impact latency/TTFB and GC pressure.

Never assume the response cache is bounded merely because the request cache was set to 1 KiB. To measure large response sizes, consider a **byte-counting** wrapper that does not retain the body, or collect metrics at another layer.

## 6. Neither API Means Body Replay

Some tutorials see the word "caching" and extrapolate:

~~~text
Read request 1st time -> request wrapper -> read request 2nd time (WRONG)
Write response -> caching response -> auto-sent to client immediately (WRONG)
~~~

In reality:

- The request wrapper is an **observer** of body reads passing through it; reading its cache accesses the **already-consumed copy** without rewinding the source.
- The response wrapper is a **buffer** of writes passing through it; once complete, data must be copied to the real response.
- Both operate inside the Servlet I/O model and do not replace reactive backpressure.
- Both can be affected by outer/inner filters wrapping request/response, execution order, and committed responses.

A genuinely replayable wrapper typically must retain a full body copy, re-implement `getInputStream` and `getReader` for repeatable reads, properly implement `ServletInputStream.isReady/isFinished/setReadListener`, and handle charsets, body limits, multipart, and async. That is a different requirement, not built-in `ContentCachingRequestWrapper` behavior.

## 7. When Should You Use vs. Avoid Them?

**Suitable when:**

- Synchronous Spring MVC/Servlet app with small, controlled bodies.
- You want to observe **lengths** of processed request/response bodies or compute an intentional checksum.
- Specific allowlisted endpoints are permitted for inspection, e.g., internal JSON without PII.
- You want test evidence that the controller read the request body and wrote the expected response bytes.
- You have policies to bound and mask data before logging or telemetry export.

**Avoid using simple sync buffering directly for:**

- Spring WebFlux reactive servers running on Reactor Netty.
- Server-Sent Events (SSE) with `text/event-stream`.
- `StreamingResponseBody`, `ResponseBodyEmitter`, and asynchronously written responses.
- Large file downloads, video streaming, or long-lived chunked transfers.
- Large multipart uploads or high-throughput binary payloads.
- APIs handling sensitive data where the only goal is dumping raw bodies.
- Responses involving layered filters like compression, ETag, caching, signing, or partial commits.
- High-memory-pressure or latency-sensitive apps without profiling.

**Note:** this is tool-selection guidance, not a claim that async can never use any caching wrapper. A properly lifecycle- and async-aware filter can be engineered, but it requires dedicated design and testing; never copy a synchronous filter and blindly widen its scope.

## 8. Sample Project: Java 17+ Spring Boot 3.5.x

This project demonstrates these limits in a testable way:

1. **POST /api/demo/echo** accepts `text/plain` and returns `ECHO:` + body; the filter measures request bytes read by the controller and response bytes generated.
2. **GET /api/demo/ping** has no request body, so the request cache is 0 bytes.
3. **POST /api/demo/length** accepts a string longer than the request cache limit; the controller still returns the full character count while the request cache keeps at most 1,024 bytes.
4. The filter **applies only to `/api/demo/`**; other endpoints do not have bodies buffered.
5. Audit records **store metadata only**, never body contents or exception messages.
6. The response body reaches the client thanks to `copyBodyToResponse()` in `finally`.

This project supports **small, synchronous endpoints** only within the demo scope. Never apply this filter to async/SSE/streaming/file downloads in production without dedicated lifecycle logic.

Structure:

~~~text
body-cache-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/cache/
    │   │   ├── BodyCacheApplication.java
    │   │   ├── EchoController.java
    │   │   ├── AuditRecord.java
    │   │   ├── AuditRecorder.java
    │   │   └── ContentCachingAuditFilter.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/cache/
            └── ContentCachingAuditTest.java
~~~

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>body-cache-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>body-cache-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Do not add `spring-boot-starter-webflux`. Spring Boot 3.5.x uses the **jakarta.servlet** package, not `javax.servlet`, in demo sources.

### 8.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: body-cache-demo
~~~

The demo contains no login data or file uploads. The request cache limit is defined in the filter class for brevity; in real applications, externalize observation limits to dedicated configuration with explicit units and environment controls.

### 8.3. BodyCacheApplication.java

~~~java
package com.example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(BodyCacheApplication.class, args);
    }
}
~~~

### 8.4. EchoController.java

~~~java
package com.example.cache;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class EchoController {

    @GetMapping(path = "/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String echo(@RequestBody String input) {
        return "ECHO:" + input;
    }

    @PostMapping(path = "/length",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Integer> length(
            @RequestBody String input) {
        return Map.of("characters", input.length());
    }
}
~~~

These methods are synchronous without `Callable`, `DeferredResult`, `StreamingResponseBody`, or reactive publishers. `echo` returns a string via Spring MVC's `StringHttpMessageConverter`, while `length` returns JSON via the corresponding converter.

In the `length` endpoint, `String.length()` counts **UTF-16 code units**, not Unicode code points or bytes. The test uses ASCII characters so `length` matches the payload byte count. For multi-byte scripts or emojis, perceived character counts can differ.

### 8.5. AuditRecord.java

~~~java
package com.example.cache;

public record AuditRecord(
        String method,
        String path,
        int requestBytesCached,
        int responseBytesCached,
        int status) {
}
~~~

This is a metadata record for the demo. It **contains no raw request or response bodies**. In production, paths can still contain sensitive IDs or query parameters; apply data-minimization policies before logging or exporting.

### 8.6. AuditRecorder.java

~~~java
package com.example.cache;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.stereotype.Component;

@Component
public class AuditRecorder {

    private final Queue<AuditRecord> records =
            new ConcurrentLinkedQueue<>();

    public void record(AuditRecord event) {
        records.add(event);
    }

    public List<AuditRecord> snapshot() {
        return List.copyOf(records);
    }

    public void clear() {
        records.clear();
    }
}
~~~

`AuditRecorder` is strictly for **test observation**. It retains events in memory unboundedly and is **not a production audit system**. For real workloads, choose metrics, tracing, or async structured logging with explicit retention, sampling, backpressure, privacy, access control, and cap policies.

### 8.7. ContentCachingAuditFilter.java

~~~java
package com.example.cache;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;

@Component
public class ContentCachingAuditFilter
        extends OncePerRequestFilter {

    private static final int REQUEST_CACHE_BYTES = 1024;

    private final AuditRecorder recorder;

    public ContentCachingAuditFilter(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI()
                .substring(request.getContextPath().length());

        return !path.startsWith("/api/demo/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        ContentCachingRequestWrapper wrappedRequest =
                new ContentCachingRequestWrapper(
                        request, REQUEST_CACHE_BYTES);

        ContentCachingResponseWrapper wrappedResponse =
                new ContentCachingResponseWrapper(response);

        try {
            chain.doFilter(wrappedRequest, wrappedResponse);
        } finally {
            try {
                recorder.record(new AuditRecord(
                        request.getMethod(),
                        request.getRequestURI(),
                        wrappedRequest.getContentAsByteArray().length,
                        wrappedResponse.getContentSize(),
                        wrappedResponse.getStatus()));
            } finally {
                wrappedResponse.copyBodyToResponse();
            }
        }
    }
}
~~~

**Why is this code correct for the synchronous demo?**

- `shouldNotFilter` narrows scope by path, avoiding buffering across the entire application.
- `REQUEST_CACHE_BYTES=1024` caps the **request copy**, without affecting the actual request.
- The filter does not call `getInputStream`/`readAllBytes` before the controller.
- Request cache data is read **after** the filter chain finishes, once `@RequestBody` has been decoded by Spring MVC.
- Response bytes are measured with `getContentSize`, avoiding allocating an extra response `byte[]`.
- The outer `finally` ensures copying is attempted after the filter chain completes; the inner `finally` ensures copying still runs even if the recorder throws.
- `copyBodyToResponse()` is indispensable so the client receives the body.

**Crucial limitation:** this filter **is only valid for controlled synchronous Servlet processing**. It does not track async lifecycles, complex error redispatches, streaming, huge bodies, or competing response wrappers. `@Component` is used here for simple Spring Boot filter registration; when explicit order, dispatcher types, and URL patterns are needed in production, prefer `FilterRegistrationBean` or intentional registration configuration. Never combine multiple registration paths for the same filter that cause it to run twice.

### 8.8. Running the Application

From the `body-cache-demo` directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Once the server listens on port 8080:

~~~bash
curl -i \
  http://localhost:8080/api/demo/ping

curl -i \
  -X POST http://localhost:8080/api/demo/echo \
  -H "Content-Type: text/plain; charset=UTF-8" \
  -H "Accept: text/plain" \
  --data-binary "hello"

curl -i \
  -X POST http://localhost:8080/api/demo/length \
  -H "Content-Type: text/plain; charset=UTF-8" \
  -H "Accept: application/json" \
  --data-binary "abc"
~~~

Exact echo body for the ASCII input in the example:

~~~text
ECHO:hello
~~~

JSON output for `length` (key order is insignificant):

~~~json
{"characters":3}
~~~

No public endpoint exposes `AuditRecorder`; it is inspected solely via injection in integration tests. This prevents exposing internal audit data over HTTP.

## 9. MockMvc Tests: Verifying Both Wrappers and the Cache Limit

**src/test/java/com/example/cache/ContentCachingAuditTest.java**

~~~java
package com.example.cache;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContentCachingAuditTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AuditRecorder recorder;

    @BeforeEach
    void resetEvents() {
        recorder.clear();
    }

    @Test
    void echoStillReachesClientAndBodiesAreObserved()
            throws Exception {

        mvc.perform(post("/api/demo/echo")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.TEXT_PLAIN)
                    .content("hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("ECHO:hello"));

        List<AuditRecord> events = recorder.snapshot();
        assertThat(events).hasSize(1);

        AuditRecord event = events.get(0);
        assertThat(event.requestBytesCached()).isEqualTo(5);
        assertThat(event.responseBytesCached()).isEqualTo(
                "ECHO:hello".getBytes(StandardCharsets.UTF_8).length);
        assertThat(event.status()).isEqualTo(200);
    }

    @Test
    void getWithoutBodyHasEmptyRequestCache() throws Exception {
        mvc.perform(get("/api/demo/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));

        List<AuditRecord> events = recorder.snapshot();
        assertThat(events).hasSize(1);
        assertThat(events.get(0).requestBytesCached()).isZero();
        assertThat(events.get(0).responseBytesCached())
                .isGreaterThan(0);
    }

    @Test
    void cacheLimitDoesNotLimitControllerInput()
            throws Exception {

        String input = "x".repeat(2048);

        mvc.perform(post("/api/demo/length")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(input))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.characters").value(2048));

        List<AuditRecord> events = recorder.snapshot();
        assertThat(events).hasSize(1);
        assertThat(events.get(0).requestBytesCached())
                .isEqualTo(1024);
    }

    @Test
    void unrelatedRouteIsNotWrapped() throws Exception {
        mvc.perform(get("/not-a-demo-route"))
                .andExpect(status().isNotFound());

        assertThat(recorder.snapshot()).isEmpty();
    }
}
~~~

**What each test verifies:**

- The `echo` test proves the response body still reaches the client, meaning `copyBodyToResponse` was not forgotten.
- The `ping` test proves a request without a body has a 0-byte request cache, even though the controller returns `"pong"`.
- The 2048-char input test proves the controller reads the entire payload while the cached request bytes stop at 1024.
- The unrelated route test proves the filter is not applied to every request.

Avoid asserting exact JSON response byte length without controlling encoding/content type, because serialization details can vary. Use ASCII and UTF-8 `text/plain` to assert byte lengths clearly.

Run:

~~~bash
mvn test
~~~

If tests pass, Maven returns exit code 0. The example has not been built inside this document; logs and timings depend on the machine and dependency set.

## 10. Why Might a Filter Still See No Body on a Request?

Common causes:

1. The controller never reads the body: the wrapper works as designed and the cache stays empty.
2. The filter was skipped by `shouldNotFilter` or a different URL mapping.
3. An **earlier** filter already read the body on the raw request before wrapping occurred.
4. The request body was read after the sync filter finished due to async processing.
5. Data came from form parameters or a multipart parser via another code path; the cache may not match every wire byte.
6. The request was rejected early by security/gateway before the body was ever consumed.
7. Another wrapper layer used the original request or altered the body stream.
8. An exception occurred before reading the body.
9. The content cache hit its limit, retaining only a prefix rather than the entire body.

**Never "fix" this by draining `ServletInputStream` inside the filter**; that starves the controller of its body. Verify which downstream code path consumes the input, check filter ordering, and confirm sync vs. async processing.

## 11. Servlet Request Parameters, Form URL Encoding, and Multipart

Requests are not always raw JSON or plain text. With form-urlencoded:

~~~http
POST /form HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&mode=basic
~~~

A servlet container may parse form parameters when `getParameterMap`/`getParameter*` is called. `ContentCachingRequestWrapper` supports capturing form parameter data under certain conditions. However, **never assume the cache always matches the raw HTTP wire body byte-for-byte** for form submissions; parameter encoding/decoding and prior parameter parsing can alter it.

For `multipart/form-data`, file uploads and metadata may be handled by the servlet container or a multipart resolver under a separate lifecycle. A bounded request cache is not a tool for measuring or preserving full uploaded file contents. Never log multipart content or uploaded bytes. If you only need upload sizes, use upload-aware multipart APIs or metrics.

### 11.1. Charset and Binary Bodies

`getContentAsString()` relies on the charset configured on the request. If a client sends byte sequences invalid for that charset or uses a binary protocol, String decoding is not guaranteed to round-trip the original payload. If you need a byte digest/hash, process only the bounded `byte[]` under a clear security policy; never assume every body is a UTF-8 string.

JSON objects can also carry passwords, tokens, card numbers, health records, or personal data. Regex masking is **not reliable enough** to guarantee sensitive data never leaks. Prefer allowlisting non-sensitive fields or recording only size, status, and request ID metadata.

## 12. Async Servlet Requests: When chain.doFilter Returns Early

Spring MVC supports `Callable`, `DeferredResult`, `WebAsyncTask`, `ResponseBodyEmitter`, and other Servlet async mechanisms. In those cases:

~~~text
T0 Filter creates request/response wrappers
T1 filterChain.doFilter(...)
T2 Controller begins async processing and returns control
T3 Filter finally executes
T4 Async worker actually completes response body (later)
~~~

Calling `copyBodyToResponse` at **T3** can happen before the final response body exists. Reading the request cache at T3 can also miss body reads in certain designs.

`OncePerRequestFilter` provides `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`. Skipping or allowing dispatches affects wrapper scope, yet **overriding these hooks alone does not solve cache and copy lifecycles**.

Proper async support requires:

- Ensuring wrappers survive across the necessary async phases.
- Handling Servlet async listeners for completion, errors, and timeouts.
- Avoiding premature or duplicate copies.
- Accounting for filter chains running again on ASYNC dispatches.
- Tracking whether the response is committed and what bytes were written.
- Testing with `DeferredResult`, `Callable`, timeouts, and mid-flight errors.

The sample app **intentionally omits Servlet async** rather than presenting a misleading "universal" solution with a broken lifecycle.

## 13. Streaming, SSE, and Large Responses: Never Buffer the Entire Stream

Imagine an endpoint:

~~~java
@GetMapping(path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    return new SseEmitter();
}
~~~

This is an illustrative Spring MVC snippet, not in the runnable demo. SSE sends events incrementally over time; wrapping it in a response cache and copying only at completion prevents events from reaching the client promptly and grows memory over long connections.

Similar scenarios:

- `StreamingResponseBody` writing chunks directly to the `OutputStream`.
- Large video or file downloads.
- Long-lived server connections and long polling.
- Proxy compression/gzip handling the response through another wrapper.
- HTTP range requests returning `206 Partial Content`.
- Attachment responses carrying binary data.

**A response wrapper without a cache cap is unsuitable for holding large bodies in memory.** To measure "how many bytes were sent," use a counting stream or metrics at the right layer instead of buffering the entire response.

Even a synchronous endpoint returning 100 MB should never be buffered if your only goal is recording the request method and response status.

## 14. Exception Management, Error Dispatches, and finally

Using `finally` for copying in a synchronous filter is crucial, yet insufficient for every error case.

If downstream throws an exception before producing a response, the Servlet container or Spring Boot may invoke an error dispatch or error rendering in another lifecycle phase. A response wrapper that buffered a partial body might hold incomplete data. Blindly copying those bytes can corrupt the error body or flush partial output.

**Therefore:**

1. The demo uses only successful synchronous controllers.
2. For production error handling, verify whether error responses are built in the same dispatch or a separate error dispatch.
3. Do not treat `shouldNotFilterErrorDispatch()` as the only thing to adjust.
4. Avoid copying a cached response body if the underlying response is already committed or undergoing a separate error dispatch unless explicitly designed for it.
5. Test `@ExceptionHandler`, `@ControllerAdvice`, `sendError`, directly thrown exceptions, and timeouts.
6. Never swallow exceptions with `catch (Exception)` and return 200 just to preserve a response body.

A response cache is not a transactional buffer. Once half a body has been written and the controller fails, network state cannot safely be rolled back.

## 15. Filter Ordering and Interactions with Spring Security, Compression, and ETag

In the Servlet stack, multiple filters wrap one another:

~~~text
Filter A -> Filter B -> DispatcherServlet -> Filter B -> Filter A
~~~

If one filter applies gzip compression, another computes an ETag, and another caches the response, **order dictates what each filter sees**: raw JSON bytes vs. compressed bytes, whether `Content-Encoding`/`Content-Length` headers are set, and whether the response has committed.

### 15.1. ShallowEtagHeaderFilter

Spring Framework includes `ShallowEtagHeaderFilter`, which uses response content caching to compute a shallow ETag from response bytes. If your app already uses that filter, adding your own response caching wrapper introduces redundant buffering layers and can break copying if managed carelessly.

If your goal is simply conditional GET or ETag support, use the built-in tool rather than writing a generic body-caching filter.

### 15.2. Spring Security

The Security filter chain can reject requests before the controller ever reads the body. If an audit filter runs after security, it misses rejected requests; if it runs before security, it could log unauthenticated requests without permission to store sensitive data.

Never read or forward the body inside a filter just for authentication when Spring Security and standard credential mechanisms exist. Never log `Authorization` headers, cookies, CSRF tokens, passwords, or raw bodies. Authorization and body caching are separate responsibilities.

### 15.3. FilterRegistrationBean and Ordering

For production use cases, register Servlet Filters explicitly with `FilterRegistrationBean` to control URL patterns and order. Never register the same filter via both `@Component` and `FilterRegistrationBean` in a way that executes it twice.

Only add `@Order` or explicit order numbers when justified and tested; filter order determines who consumes the request body, whether the response body is already encoded/compressed, and which filter sees exceptions.

## 16. Comparison with HandlerInterceptor

Spring MVC's **HandlerInterceptor** wraps MVC handlers. It is well suited for observing:

- handler method/route;
- request start/end timing;
- status and handler metadata;
- data that does not depend on the raw body.

However, an interceptor does not wrap Servlet request/response streams the way a Filter does. When byte-level body observation is required, a filter is usually the right layer, provided its lifecycle is respected.

`preHandle`, `postHandle`, and `afterCompletion` do not guarantee access to a buffered response body; moreover, `postHandle` does not execute as newcomers often expect with `@ResponseBody` or async processing.

If your goal is solely "per-route latency," prefer Micrometer observations or a `HandlerInterceptor` instead of buffering the response body.

## 17. Comparison with Spring WebFlux

`ContentCachingRequestWrapper` and `ContentCachingResponseWrapper` use:

~~~java
jakarta.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletResponse
~~~

In a reactive WebFlux server application:

~~~java
org.springframework.http.server.reactive.ServerHttpRequest
org.springframework.http.server.reactive.ServerHttpResponse
org.springframework.web.server.ServerWebExchange
~~~

These are **different abstractions**. WebFlux has no `ServletInputStream` or `ServletOutputStream` as its primary API. Never force `ContentCachingRequestWrapper` inside a Reactor Netty `WebFilter`.

If body observation is mandatory in WebFlux, build appropriate decorators (`ServerHttpRequestDecorator`/`ServerHttpResponseDecorator`) with full understanding of `DataBuffer`, reference counting, reactive streams, backpressure, cancellation, and codecs. That design must bound memory and preserve subscriptions; never copy Servlet filter code verbatim into a `WebFilter`.

**Note when both Spring Boot starters are present:** if a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot normally selects MVC/Servlet unless configured otherwise. Having `WebClient` or WebFlux on the classpath does not automatically mean the server runs reactive.

## 18. Safer Alternatives

| Actual Goal | Better Alternative |
|---|---|
| Measure request count/status/latency | Micrometer HTTP server observations |
| Audit business actions | Application-service events with allowlisted fields |
| Trace requests across services | Distributed tracing, trace ID, correlation ID |
| Log method, URI, selective headers | `CommonsRequestLoggingFilter` or minimal filter without body |
| Log tiny, redacted request body prefix | `AbstractRequestLoggingFilter`/`CommonsRequestLoggingFilter` with strict max payload and privacy review |
| Compute ETag for eligible responses | `ShallowEtagHeaderFilter` or framework HTTP caching |
| Count large response bytes | Counting output stream/metrics at the proper layer without buffering raw body |
| Validate JSON schema | DTOs + Jakarta Validation + business checks |
| Reject oversized uploads/bodies | Servlet container, gateway, endpoint/server limits; never rely on request cache limit |
| Read request body multiple times | Dedicated bounded replay wrapper preserving Servlet semantics |
| Observability for WebFlux | `WebFilter`/reactive observations, never Servlet wrappers |

Do not choose body caching merely because it is easy to demo. Choose the solution requiring the least data access and causing the lowest latency overhead that satisfies operational needs.

## 19. Operations and Security Checklist

Before deploying any filter that touches request/response bodies, answer:

- [ ] Does the app run Spring MVC/Servlet rather than a WebFlux reactive server?
- [ ] Do we truly need the body, or just request ID/method/status/latency?
- [ ] Are the wrapped URLs, HTTP methods, and content types strictly bounded?
- [ ] Is the request cache limit set in bytes and not confused with max request size?
- [ ] Do consumers understand `getContentAsByteArray()` can be empty or a prefix only?
- [ ] Is `getInputStream()` never read before the controller just to populate the cache?
- [ ] Does the response wrapper invoke `copyBodyToResponse()` in the proper lifecycle?
- [ ] Are tests verifying the response body reaches the client intact after filtering?
- [ ] Are async, streaming, SSE, and large uploads/downloads excluded?
- [ ] Have error dispatches, timeouts, `sendError`, and committed responses been considered?
- [ ] Have compression, ETag, caching, gateway, and Spring Security filter ordering been verified?
- [ ] Are raw credentials, Authorization, cookies, tokens, PII, and financial/health data kept out of logs?
- [ ] Are retention, masking, access control, sampling, and bounded memory defined?
- [ ] Do tests send payloads larger than the request cache limit to prove the controller still reads everything?
- [ ] Have load/concurrency tests measured response-buffer memory and latency impact?
- [ ] Is the filter registered only once (not duplicated across `@Component` and `FilterRegistrationBean`)?
- [ ] Is there an explicit strategy for multipart/form-urlencoded and charsets?
- [ ] Are HEAD, 204 No Content, and empty-body responses tested if in scope?

## 20. Common Mistakes and Fixes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Request cache always empty | Read cache before chain or controller never reads body | Read after downstream; verify actual execution path |
| Controller `@RequestBody` receives empty | Filter read `InputStream` before controller | Stop reading early; use dedicated replay wrapper if required |
| Cache holds only 1024 bytes on 2048 payload | `contentCacheLimit` caps the copy only | Never report it as truncation of the actual request |
| Client receives empty response body | Forgot `copyBodyToResponse` | Copy in proper sync lifecycle, including `finally` |
| Called `flushBuffer` yet client still gets no body | Response wrapper `flushBuffer` does not copy cached body | Call `copyBodyToResponse` |
| Memory spikes on large downloads | Response wrapper buffers entire output | Exclude large files; use counting/metrics |
| SSE events do not arrive incrementally | Body held inside wrapper | Remove response buffering or build streaming-aware logic |
| 2048 Unicode chars differ from cached byte count | Multi-byte UTF-8/charset encoding | Distinguish bytes, code units, and code points |
| JSON logs contain passwords/tokens | Logged raw request/response bodies | Disable raw body logging, allowlist metadata, run privacy review |
| Breaks with async/`DeferredResult` | `chain.doFilter` returns before async finishes | Build async-aware lifecycle; do not reuse sync template |
| Weird 500/error body after filter | Error dispatch, committed response, or misplaced copy | Test exception handling and dispatch types |
| Mismatched `Content-Length` | Multiple wrappers, premature copy, compression | Inspect filter ordering, copying, and headers |
| Certain endpoints skip auditing | `shouldNotFilter`/URL pattern or earlier security rejection | Verify scope and filter ordering |
| WebFlux project fails to compile with wrapper | Imported Servlet wrapper into reactive server | Use reactive request/response decorators instead |
| Multipart cache differs from wire body | Container parser/form semantics | Observe multipart at the right layer |
| `AuditRecorder` grows memory unboundedly | Demo stores an unbounded `Queue` | Use bounded metrics/logging infrastructure |
| Logging failures disrupt HTTP responses | Audit/metrics throw inside filter | Isolate audit failures and prioritize preserving the HTTP response |

## 21. Timeline Debugging Mental Model

When debugging a caching-wrapper bug, trace these timestamps:

~~~text
T0 Request starts: URL/method/content type?
T1 Did the filter actually run? Before/after which other filters?
T2 Who holds the request wrapper? Did anyone read InputStream?
T3 Does any @RequestBody or converter read the body?
T4 Does the controller return sync, async, stream, or throw?
T5 How many bytes did the response writer write to the wrapper?
T6 Did filterChain.doFilter() actually finish synchronously?
T7 Was copyBodyToResponse() called? Was the response already committed?
T8 What status/headers/body did the client actually receive?
~~~

Effective techniques:

- Use MockMvc to test sync filters and controllers.
- Use integration tests with an embedded server to observe network, compression, and chunked/async semantics.
- Use fixed-length ASCII payloads to distinguish byte counts from character counts.
- Assert on the actual response body, not just HTTP 200.
- Never rely solely on logs to conclude a request was fully read.
- Test bodies larger than the cache limit to verify the limit does not truncate controller input.
- Test raw text, JSON, form data, and multipart separately when genuinely supported.
- Use profiling and metrics to evaluate response-caching memory overhead.

## 22. Conclusion

**`ContentCachingRequestWrapper`** keeps a **bounded copy** of request bytes already read downstream. It **does not proactively consume the body** and **does not let the controller re-read the request arbitrarily**. `contentCacheLimit` caps the copy only, not the actual request/upload size.

**`ContentCachingResponseWrapper`** buffers bytes written downstream into the wrapper. For the client to receive the response, you **must call `copyBodyToResponse()`** at the right moment. It has no corresponding constructor cap and can drive up memory and latency on large or streaming responses.

In Spring Boot MVC/Servlet, they are suitable for **synchronous, small-body endpoints with controlled data**. Never push a synchronous filter onto async/SSE/streaming endpoints merely by adding a couple of hooks; a different design is required. For production logging/metrics, favor minimal metadata, explicit bounds, no sensitive body storage, and real lifecycle testing.

## Official Documentation

- [Spring Framework 6.2 — ContentCachingRequestWrapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html)
- [Spring Framework 6.2 — ContentCachingResponseWrapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/ContentCachingResponseWrapper.html)
- [Spring Framework 6.2 — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)