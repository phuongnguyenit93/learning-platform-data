# Request Body Re-Read Limits and Using Wrappers or Decorators in Spring Boot

## 1. Problem: Request Bodies Are Not Replayable Buffers by Default

An HTTP request body arrives at the server as a stream of bytes. In Spring Boot, the framework normally consumes that stream to decode JSON, form data, multipart payloads, or binary data. Once one component finishes reading it, the next component cannot automatically rewind to the first byte.

In **Spring MVC**, the request body is read via HttpServletRequest.getInputStream() or getReader(). When a controller declares @RequestBody, an HttpMessageConverter reads the stream to construct a Java DTO. A Servlet Filter or HandlerInterceptor that reads ahead without replaying the bytes can leave the controller with an empty body, Required request body is missing, or JSON parse errors.

In **Spring WebFlux**, ServerHttpRequest.getBody() returns Flux<DataBuffer>. Having a WebFilter subscribe to and consume the original Flux does not mean the controller can subscribe again and receive the exact original payload. The incoming network stream publisher is not a cache with guaranteed replay.

Practical needs include auditing, measuring size, verifying webhook signatures, validating formats, troubleshooting, or middleware processing. Not every use case requires reading the body twice. Prioritize:

1. If you only need to log metadata, do not read the raw body.
2. If you want to observe bytes as the controller reads them, use an observation-caching mechanism.
3. If two consumers genuinely need to read the same raw bytes, buffer with strict size bounds and replay through a wrapper/decorator.
4. Once parsed into a DTO, pass the DTO forward instead of reparsing raw bytes a second time.
5. For large files or unbounded streams, use streaming or managed temporary storage; avoid buffering the entire payload in RAM.

**Core principle:** a body does not automatically support seek, rewind, or replay. To support rereading, the application must provide a fresh data source with explicit size limits and lifecycle management.

## 2. Servlet MVC and WebFlux Use Different Abstractions

| Aspect | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Incoming request | HttpServletRequest | ServerHttpRequest |
| Reading body | getInputStream(), getReader() | getBody(): Flux<DataBuffer> |
| Global extension point | Servlet Filter / OncePerRequestFilter | WebFilter |
| Wrapping mechanism | HttpServletRequestWrapper | ServerHttpRequestDecorator |
| Parsing @RequestBody | HttpMessageConverter | HttpMessageReader/Decoder |
| Built-in observation tool | ContentCachingRequestWrapper | Do not use Servlet wrappers; use an appropriate reactive pipeline |
| Replaying body | New ByteArrayInputStream from cached byte[] | New Flux<DataBuffer> from cached bytes |
| Specific risks | Form parsers, Servlet async input, filter order | Pooled buffers, retain/release, cancellation, backpressure |

Examples in this lesson target **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. Boot 3 uses the jakarta.servlet package; legacy Boot 2 used javax.servlet. A project that includes spring-webflux solely for WebClient can still run MVC, so verify the actual web application type before selecting code.

## 3. Distinguishing Body Observation from Body Replay

**Observation** means recording a copy of the bytes that downstream code actually reads. If downstream never reads, the cache stays empty. If downstream reads only part of the body, the cache holds only that portion. Observation does not rewind the underlying request stream.

**Replay** means providing a body source independent of the current read position. With a simple wrapper, you store small payloads in a byte[] and create a fresh ByteArrayInputStream on each call to getInputStream(). In WebFlux, a decorator emits a fresh Flux for each subsequent subscriber.

| Need | Suitable approach |
|---|---|
| Log the number of bytes downstream consumed | ContentCachingRequestWrapper after the Filter chain |
| Log actual size and reject oversized payloads | Body limits at proxy/server plus bounded reading |
| Filter verifies raw JSON, controller still uses @RequestBody | Bounded replay wrapper |
| WebFlux WebFilter inspects raw JSON, controller still parses | Bounded aggregate + ServerHttpRequestDecorator |
| Controller already has the DTO and needs business checks | Use the DTO, validation, and service—do not reread the stream |
| Multi-GB multipart uploads | Streaming, disk/object storage, and quotas; never replay in a byte[] |

Avoid applying the same strategy to every endpoint. Retaining copies of full payloads across thousands of concurrent requests creates severe memory pressure and latency spikes.

## 4. ContentCachingRequestWrapper: Caches Read Bytes, Does Not Replay Automatically

Spring Framework provides:

~~~java
org.springframework.web.util.ContentCachingRequestWrapper
~~~

Per the 6.2 Javadoc, this class caches content **as** the InputStream/Reader is read. It does not proactively read the body in its constructor. getContentAsByteArray() returns the bytes cached so far, up to the cache limit.

Several consequences follow:

- Before the controller reads @RequestBody, getContentAsByteArray() is typically empty.
- If the controller never reads the body, the cache stays empty even though the client sent data.
- If the controller reads only part of the body, the cache will also be partial.
- contentCacheLimit does not reject requests exceeding the limit; it caps how many bytes are retained in the cache.
- The handleContentOverflow(int) hook can be overridden for custom overflow handling, yet default behavior is not automatically HTTP 413.
- This class does not guarantee that a second getInputStream() call replays all bytes for another consumer.

Example Filter that only **observes the byte count** after MVC processes the request:

~~~java
package example.mvc;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;

@Component
public class ObservedBodyFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(ObservedBodyFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        ContentCachingRequestWrapper wrapped =
                new ContentCachingRequestWrapper(request, 4096);

        try {
            chain.doFilter(wrapped, response);
        } finally {
            log.debug("Cached body bytes: {}",
                    wrapped.getContentAsByteArray().length);
        }
    }
}
~~~

This Filter does not read the body before the controller runs. When the controller reads it, the wrapper keeps up to 4096 bytes. The logged value can be smaller than the true total payload due to the cache limit or partial downstream reads; it is not an absolute measurement of payload length.

**Note:** Do not register ObservedBodyFilter and the full replay Filter from the next section simultaneously on the same endpoint without controlling filter ordering and nested wrapper behavior. The two examples address **two different use cases**.

## 5. Why an Early Read Causes @RequestBody to Fail

Broken Filter example:

~~~java
byte[] bytes = request.getInputStream().readAllBytes();
log.debug("Read {} bytes", bytes.length);
chain.doFilter(request, response);
~~~

The Filter read the original stream to EOF; afterward MVC's HttpMessageConverter has no remaining data to parse. If the controller requires @RequestBody, Spring reports a missing request body or parse failure.

Wrapping with ContentCachingRequestWrapper is still insufficient if the Filter reads first and expects data to remain for the controller:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request);
byte[] bytes = wrapped.getInputStream().readAllBytes();
chain.doFilter(wrapped, response);
~~~

Here wrapped.getInputStream() still consumes the underlying input while caching, and ContentCachingRequestWrapper does not promise that subsequent getInputStream calls restart from byte zero. When middleware must read ahead and the controller must read again, you need a truly **replayable** wrapper or must move the logic after framework parsing.

If the goal is JSON validation, @Valid on a DTO or RequestBodyAdvice is usually far better than intercepting raw bytes.

## 6. Custom Servlet Wrapper for Body Replay in Synchronous Processing

For small JSON endpoints, you can read the original body **once with a size bound** in a Filter, then pass an HttpServletRequestWrapper down the chain that creates fresh streams from the stored bytes.

The example below is strictly for **synchronous Servlet reads**; it does not implement the non-blocking ServletInputStream.setReadListener contract. This is noted explicitly so it is never mistaken for async I/O support.

### 6.1. File ReplayableRequest.java

File src/main/java/example/mvc/ReplayableRequest.java:

~~~java
package example.mvc;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

public final class ReplayableRequest extends HttpServletRequestWrapper {

    private final byte[] body;

    public ReplayableRequest(HttpServletRequest original, byte[] bytes) {
        super(original);
        this.body = bytes.clone();
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream input = new ByteArrayInputStream(body);

        return new ServletInputStream() {
            @Override
            public int read() throws IOException {
                return input.read();
            }

            @Override
            public boolean isFinished() {
                return input.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException(
                        "Synchronous reads only");
            }
        };
    }

    @Override
    public BufferedReader getReader() throws IOException {
        String encoding = getCharacterEncoding();
        Charset charset = encoding == null
                ? StandardCharsets.UTF_8
                : Charset.forName(encoding);
        return new BufferedReader(
                new InputStreamReader(getInputStream(), charset));
    }
}
~~~

Key points:

- The constructor clones byte[] to prevent unintended mutation.
- getInputStream() creates a fresh ByteArrayInputStream starting at byte 0 on **every call**.
- getReader() also creates a fresh reader, honoring the request's declared encoding with UTF-8 fallback.
- isFinished reports whether the stream reached EOF; isReady returns true because the bytes reside in RAM.
- setReadListener intentionally throws unsupported. If the application uses non-blocking Servlet request input or Servlet async APIs, replace this with a full ReadListener implementation or an alternative design.
- The wrapper does not override getParameter(), getParts(), or getParameterMap(). Therefore never apply it blindly to application/x-www-form-urlencoded or multipart/form-data, where the container runs its own parser.

Do not treat this wrapper as a complete Servlet framework: it is a focused design example for replaying small JSON bodies in synchronous requests.

## 7. Servlet Filter with Bounded Read Returning HTTP 413

File src/main/java/example/mvc/ReplayBodyFilter.java:

~~~java
package example.mvc;

import java.io.IOException;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ReplayBodyFilter extends OncePerRequestFilter {

    private static final int MAX_BYTES = 64 * 1024;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String contentType = request.getContentType();
        boolean target = "POST".equalsIgnoreCase(request.getMethod())
                && "/api/echo".equals(request.getServletPath())
                && contentType != null
                && contentType.toLowerCase(Locale.ROOT)
                        .startsWith("application/json");

        if (!target) {
            chain.doFilter(request, response);
            return;
        }

        // Read up to MAX_BYTES + 1 to detect an oversized body.
        byte[] bytes = request.getInputStream()
                .readNBytes(MAX_BYTES + 1);

        if (bytes.length > MAX_BYTES) {
            response.sendError(413, "Request body too large");
            return;
        }

        chain.doFilter(new ReplayableRequest(request, bytes), response);
    }
}
~~~

**Why read MAX_BYTES + 1?** If you only read 64 KiB, you cannot tell whether byte 65,537 exists in the stream. Reading at most one byte past the threshold is enough to reject oversized payloads without loading an entire huge request into RAM.

Do not rely solely on Content-Length for enforcement because the header may be absent or requests may use chunked transfer encoding. To defend against slow uploads, also configure server/proxy read timeouts and related limits.

This Filter intentionally targets only POST /api/echo with application/json. If the project uses a context path or custom servlet mapping, verify getServletPath() in that environment. For complex Content-Type headers, use a proper MediaType parser and error handling; startsWith is merely a simple condition for this endpoint example.

This Filter creates a copy per accepted request. Before applying it API-wide, calculate memory budgets, concurrency, body limits, and DoS protections; never flip target to true for all requests without evaluating the cost.

## 8. Controller Proving JSON Was Decoded and Can Still Be Reread

File src/main/java/example/mvc/BodyEchoController.java:

~~~java
package example.mvc;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BodyEchoController {

    public record Payload(String message) {}

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> echo(
            @RequestBody Payload payload,
            HttpServletRequest request) throws IOException {

        // MVC has already read JSON to build Payload before entering this method.
        byte[] replayed = request.getInputStream().readAllBytes();

        String message = payload.message() == null
                ? ""
                : payload.message();

        return Map.of(
                "message", message,
                "replayedBytes", replayed.length
        );
    }
}
~~~

From the client:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'
~~~

Expected HTTP 200, JSON body equivalent to:

~~~json
{"message":"hello","replayedBytes":19}
~~~

19 is the exact byte length of the ASCII JSON string in this example, not a general limit or Unicode character count. Key ordering in the JSON response may vary.

The controller rereads the body only to demonstrate the wrapper. In business code, once Payload is available, use Payload rather than reading raw bytes again.

### 8.1. Maven Project Structure

Spring Boot 3.5 / Java 17+ project with starter-web and starter-test:

~~~xml
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
~~~

The snippet above belongs inside pom.xml with the Spring Boot parent/BOM. Application class:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

Place the Java files under src/main/java/example/mvc/ and tests under src/test/java/example/mvc/. This example is not a standalone javac program because it depends on Spring Boot and the Servlet API.

### 8.2. MockMvc Tests for Replay and Size Limits

File src/test/java/example/mvc/ReplayBodyFilterTest.java:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ReplayBodyFilterTest {

    @Autowired
    MockMvc mvc;

    @Test
    void converterAndControllerBothReceiveBytes() throws Exception {
        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("hello"))
                .andExpect(jsonPath("$.replayedBytes").value(19));
    }

    @Test
    void rejectsBodyBeyondLimit() throws Exception {
        String large = "{\"message\":\""
                + "x".repeat(64 * 1024)
                + "\"}";

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(large))
                .andExpect(status().is(413));
    }
}
~~~

Run ./mvnw test or on Windows .\mvnw.cmd test. The first test verifies @RequestBody received the JSON and the subsequent getInputStream read returned all 19 bytes. The second test verifies payloads exceeding 64 KiB are rejected by the Filter.

If you enable Spring Security, MockMvc may receive 401/403 before reaching the controller; configure security policies and test identities properly rather than concluding the replay wrapper failed.

## 9. Limitations of Replay Wrappers on Servlet

### URL-Encoded Forms

application/x-www-form-urlencoded has special parsing semantics in Servlet containers. If a Filter reads InputStream early, calls to getParameter()/getParameterMap() can be affected. ReplayableRequest supports only streams and readers and does not reconstruct form parameter maps.

If form support is required, use APIs after form parsing or build a wrapper that fully preserves parameter semantics, charsets, and read timing; never reuse the JSON wrapper verbatim.

### Multipart Uploads

Multipart bodies contain multiple parts, headers, and files. Buffering the whole request can cause OutOfMemoryError or heavy heap consumption under concurrent uploads. Let the multipart resolver/Part API handle it, set max file/request sizes, and use disk/object storage as needed. Never log file contents just for debugging.

### Async Servlet API

With Servlet 3.1 non-blocking I/O, setReadListener must honor asynchronous callback contracts. ReplayableRequest above throws UnsupportedOperationException, so **use it only for synchronous reads**. With Callable, DeferredResult, WebAsyncTask, or async dispatches, you must also evaluate Filter, wrapper, and callback lifecycles.

### InputStream and Reader

The Servlet API restricts mixing getInputStream and getReader. The example wrapper intentionally provides fresh sources for both, yet is not a universal solution for every container/framework quirk. Prefer a single consistent way to read raw bytes, preserve encoding, and avoid mixing form, multipart, and raw stream parsers.

### Filter Ordering

If an earlier Filter consumed the body before ReplayBodyFilter ran, the wrapper cannot recover lost bytes. Audit the order of Servlet filters, Spring Security, and other middleware. Any ordering change requires integration tests; never crank filter order arbitrarily without understanding security consequences.

## 10. WebFlux: Why Subscribing Twice to the Original Body Is Unreliable

In WebFlux:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

This is a publisher representing incoming request bytes, not an in-memory List<DataBuffer>. If a WebFilter reads via subscribe() or DataBufferUtils.join(...), the body is consumed along the pipeline. The controller will not automatically receive the same data again when invoking @RequestBody.

Flawed design:

~~~java
exchange.getRequest().getBody().subscribe(buffer -> {
    // Read bytes here...
});
return chain.filter(exchange);
~~~

Manual subscribe() detaches reading from the chain lifecycle, breaking backpressure, error propagation, cancellation, and DataBuffer ownership. Always **return a Mono composing the read, decorator creation, and chain.filter call**, never a side-effect subscription.

WebFlux uses ServerHttpRequestDecorator to override getBody() and return a new publisher:

~~~java
ServerHttpRequestDecorator replay =
        new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public Flux<DataBuffer> getBody() {
                // Return a new Flux per the application's replay contract.
                return ...;
            }
        };

return chain.filter(exchange.mutate()
        .request(replay)
        .build());
~~~

This illustrates the concept; the complete code in the next section adds the 64 KiB limit, DataBuffer release, and HTTP 413 handling.

## 11. WebFlux WebFilter: Bounded Join and ServerHttpRequestDecorator

### 11.1. Design

Sequence:

1. Apply only to POST /api/echo with application/json.
2. Read request.getBody() via DataBufferUtils.join(..., 64 KiB).
3. If the limit is exceeded, map DataBufferLimitException to ResponseStatusException(413).
4. Copy the joined DataBuffer into a byte[] and release the original buffer in finally.
5. Create a ServerHttpRequestDecorator where each subscriber receives a fresh DataBuffer wrapping the bytes.
6. Call chain.filter(exchange with mutated request) within the same reactive pipeline.

Copying to a byte[] simplifies reference-count management compared to retaining a pooled DataBuffer across multiple subscribers. However, it incurs extra allocation and is suited only to small requests.

### 11.2. File ReplayBodyWebFilter.java

File src/main/java/example/flux/ReplayBodyWebFilter.java:

~~~java
package example.flux;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ReplayBodyWebFilter implements WebFilter {

    private static final int MAX_BYTES = 64 * 1024;

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        ServerHttpRequest request = exchange.getRequest();
        MediaType contentType = request.getHeaders().getContentType();

        boolean target = request.getMethod() == HttpMethod.POST
                && request.getPath().pathWithinApplication()
                        .value().equals("/api/echo")
                && contentType != null
                && MediaType.APPLICATION_JSON
                        .isCompatibleWith(contentType);

        if (!target) {
            return chain.filter(exchange);
        }

        Mono<byte[]> cached = DataBufferUtils.join(
                        request.getBody(), MAX_BYTES)
                .map(buffer -> {
                    try {
                        byte[] bytes =
                                new byte[buffer.readableByteCount()];
                        buffer.read(bytes);
                        return bytes;
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .defaultIfEmpty(new byte[0])
                .onErrorMap(
                        DataBufferLimitException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "Request body too large", ex));

        return cached.flatMap(bytes -> {
            ServerHttpRequestDecorator replay =
                    new ServerHttpRequestDecorator(request) {
                @Override
                public Flux<DataBuffer> getBody() {
                    return Flux.defer(() -> Flux.just(
                            exchange.getResponse()
                                    .bufferFactory()
                                    .wrap(bytes.clone())));
                }
            };

            return chain.filter(exchange.mutate()
                    .request(replay)
                    .build());
        });
    }
}
~~~

Explanation:

- join(Publisher, maxByteCount) caps the total aggregated bytes. On error or cancellation, already-joined buffers are released per the DataBufferUtils contract.
- map copies bytes and releases the joined buffer, avoiding holding pooled input longer than necessary.
- defaultIfEmpty handles requests emitting no DataBuffers.
- onErrorMap sits in the body-reading pipeline before the downstream flatMap, converting buffer-limit errors specifically into HTTP 413.
- Flux.defer provides a fresh DataBuffer per subscription; bytes.clone() prevents multiple subscribers from sharing a mutable array.
- Downstream codecs are responsible for consuming and releasing the new DataBuffer along the HTTP flow.
- Never call block(), subscribe() manually, or store raw bytes in a static/global cache.
- The Filter still disables true streaming because it buffers the entire small JSON request before calling the controller; never apply it to uploads or unbounded streams.

With Netty, direct DataBuffer manipulation requires strict lifecycle handling. A released DataBuffer must never be re-emitted via Flux.just(buffer) to another subscriber. If using retain(), match it with the exact required number of releases. Copying into a bounded byte[] reduces the risk of reusing released buffers.

## 12. WebFlux Controller and WebTestClient Example

Create a **separate Spring Boot 3.5.x project** with Java 17+, spring-boot-starter-webflux, and spring-boot-starter-test. Do not copy ReplayableRequest from the Servlet project into a reactive-only application.

File src/main/java/example/flux/FluxApplication.java:

~~~java
package example.flux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxApplication.class, args);
    }
}
~~~

File src/main/java/example/flux/FluxEchoController.java:

~~~java
package example.flux;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class FluxEchoController {

    public record Payload(String message) {}

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<Payload> body) {
        return body.map(payload ->
                Map.of("message", payload.message() == null
                        ? "" : payload.message()));
    }
}
~~~

The controller reads only once after the WebFilter has cached the body. It needs no awareness of DataBuffer because HttpMessageReader decodes the JSON from the decorator.

File src/test/java/example/flux/ReplayBodyWebFilterTest.java:

~~~java
package example.flux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReplayBodyWebFilterTest {

    @Autowired
    WebTestClient client;

    @Test
    void bodyStillReachesController() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"message\":\"hello\"}")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void largeBodyIsRejected() {
        String big = "{\"message\":\""
                + "x".repeat(64 * 1024)
                + "\"}";

        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(big)
                .exchange()
                .expectStatus().isEqualTo(413);
    }
}
~~~

Run ./mvnw test or .\mvnw.cmd test. WebTestClient works with the full reactive context and embedded server. If the project includes Spring Security, configure appropriate identity/policy rules so 401/403 is not mistaken for a body-decorator error.

When testing WebFlux separately, verify spring-boot-starter-web is not unintentionally present: if both starters exist, Boot normally selects MVC instead of WebFlux.

## 13. DataBuffer Ownership, Memory Limits, and Backpressure

These are high-risk mistakes when writing WebFlux filters:

1. DataBuffers from Reactor Netty can be pooled and reference-counted; release them when you finish consuming them yourself.
2. DataBufferUtils.join can create a composite buffer; release the resulting buffer once read, including on exception paths.
3. When buffers are discarded due to cancellation, filters, or flatMap, you may need doOnDiscard(DataBuffer.class, DataBufferUtils::release) per Spring guidance.
4. If holding a pooled DataBuffer past a callback, retain first and release the matching number of times afterward.
5. Never reuse a DataBuffer already released by the framework.
6. Never manually subscribe to the request body outside the chain; let Reactor drive subscription and cancellation.
7. Never retain multiple copies of payloads in logs, caches, request attributes, or unbounded queues.

Anti-pattern:

~~~java
DataBuffer cachedBuffer = ...;
// May be released after the first subscriber:
Flux<DataBuffer> replay = Flux.just(cachedBuffer);
~~~

If the first subscriber consumes and releases cachedBuffer, a subsequent subscriber can fail with a reference-count error. Using a bounded byte[] and wrapping a new buffer per subscription avoids coupling to a released pooled buffer, though RAM and allocation costs still must be budgeted.

### Codec Limits Do Not Replace Custom Filter Limits

In Spring Boot WebFlux, you can configure codecs, for example:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
~~~

The codec limit governs codec buffering/aggregation under codec semantics. It **does not automatically enforce a limit on custom WebFilters calling DataBufferUtils.join** unless the Filter passes maxByteCount.

In the WebFilter example, MAX_BYTES = 64 KiB operates independently. Payloads exceeding this threshold receive 413 even if the HTTP codec allows a larger size.

Enforce layered limits at the reverse proxy/API gateway, server, multipart parser, JSON codec, and application layer as appropriate. Never raise maxInMemorySize endlessly just to silence DataBufferLimitException.

## 14. RequestBodyAdvice, Logging, and Avoiding Rereading Bytes

If the requirement is validating a decoded object, Spring MVC provides RequestBodyAdvice and Bean Validation. Using @Valid with a DTO or service validation is usually cleaner than reading raw JSON in a Filter and reparsing it in the controller.

HandlerInterceptor can inspect handler metadata and request metadata, yet calling request.getInputStream() directly in preHandle still consumes the stream. In WebFlux, use WebFilter and exchange attributes to share processed metadata rather than adding extra body subscriptions.

If auditing only requires request size, content type, and status, collect those after the controller/codec reads the body or at the HTTP server/proxy layer rather than copying raw payloads into logs.

For **webhook signatures** requiring HMAC over the raw body, never re-serialize a DTO back to JSON for verification: whitespace, escaping, and field order can change and break the HMAC. When signature verification is required, read the raw bytes with strict size bounds at one intentional spot, verify using constant-time comparison, and replay if downstream needs to parse the same bytes. Never log secret keys, signatures, or sensitive payloads.

## 15. Multipart, Forms, Unicode, and Key Limitations

**URL-encoded forms:** Servlet containers can parse parameters from the request body. If a Filter reads InputStream before getParameter is called, the parameter map can break. The example wrapper does not reconstruct getParameter()/getParts() and must not be used broadly for forms or multipart requests.

**Multipart:** MultipartFile and Part APIs have dedicated lifecycle and storage semantics. Building a giant byte[] from an entire multipart upload just to log it is inappropriate. Use streaming, file size limits, disk quotas, and object storage.

**Unicode:** UTF-8 byte length does not necessarily equal Java String.length(). For Vietnamese text, emoji, or non-ASCII encodings, enforce max request size in bytes, not characters. getReader must respect the charset; modern JSON typically uses UTF-8.

**Content-Length:** May be absent or may not reflect actual bytes read across proxies and encodings. Enforce limits by counting actual bytes read rather than trusting request.getContentLengthLong() alone.

**Non-blocking Servlet async:** ReplayableRequest in the example does not support setReadListener. A non-blocking implementation must fulfill the full callback contract; merely returning isReady=true does not make it compatible with every framework mode.

**Client disconnect/cancellation:** WebFlux pipelines can cancel mid-stream. Accumulated DataBuffers must be released; never retain partial bodies in a global cache after cancellation. In Servlet, read errors and timeouts must also release resources cleanly.

## 16. Common Errors and Root Causes

| Symptom | Possible cause | Fix |
|---|---|---|
| @RequestBody reports missing after adding Filter | Filter read the body before controller | Remove early read, or use bounded replay wrapper |
| getContentAsByteArray() is empty in Filter | Downstream has not read the body yet | Observe after chain runs, not as read-ahead |
| Cache holds only part of the body | Cache limit or partial downstream read | Never treat cache length as exact payload length |
| ContentCachingRequestWrapper used, yet second read is empty | Wrapper does not promise stream replay | Use a wrapper creating fresh getInputStream instances |
| application/x-www-form-urlencoded has no parameters | Filter read body before form parser | Use appropriate form APIs; avoid JSON wrapper |
| Multipart upload causes OutOfMemoryError | Entire file buffered in heap | Streaming, disk/object storage, and quotas |
| Vietnamese JSON has garbled characters | Bytes decoded with wrong charset | Use UTF-8 or the declared charset |
| WebFlux controller receives empty body | WebFilter subscribed to original body early | Bounded aggregation + request decorator |
| Netty reports memory leak | DataBuffer not released after consumption | Audit join, release, and cancellation paths |
| WebFlux Invalid reference count | Reused a released pooled buffer | Allocate fresh DataBuffer or manage retain/release |
| DataBufferLimitException | Codec/join exceeded threshold | Set intentional limits, handle 413, budget memory |
| Oversized payload still accepted | Only set ContentCaching cacheLimit | Enforce actual byte limit at proxy/server/filter |
| Servlet async InputStream callback error | Blocking-only wrapper | Use an implementation honoring Servlet async contracts |
| Filter applied too broadly | Caches every path including uploads | Restrict by media type, method, and endpoint |
| Controller fine, but wrong filter order | Earlier filter already consumed body | Check Filter registration/order and Spring Security |
| System slows down under high load | Every request copies body into RAM | Cap size, concurrency, GC impact, or stream |

When debugging, identify the **first consumer** of the body. If Consumer A read before the wrapper was created, a wrapper added afterward cannot restore the original bytes. When Security Filters or middleware touch the body, execution order is critical.

## 17. Security and Memory Budgeting

Request bodies can contain passwords, tokens, OTPs, emails, financial data, personal information, or files. Replaying creates extra copies of this data in the heap.

Guidelines:

- Never log entire request bodies by default in production.
- Never retain raw bodies in static fields, sessions, or shared caches lacking lifecycles.
- Whitelist/mask fields before logging; prefer request metadata and processed byte counts.
- Buffer only the media types and endpoints that strictly require it.
- Enforce both **byte** limits and request concurrency limits. Under high concurrency, total RAM scales with body size × concurrent requests × copy count.
- Avoid retaining raw bodies longer than the request lifecycle; do not rely on GC timing to satisfy sensitive-data retention policies.
- Never apply the same buffering strategy to large file uploads or unbounded streams.
- Test 413, invalid JSON, empty bodies, timeouts, client cancellation, excluded multipart routes, and security policies.
- Audit logging and tracing so raw bodies are not accidentally copied into trace attributes.

Example: 1,000 concurrent requests each holding a 64 KiB body takes roughly 62.5 MiB for just a single copy, before counting object overhead, decoder buffers, extra copies, and GC. Even a small per-request cap is not harmless at high concurrency.

## 18. Practical Implementation Workflow

1. **Identify the web stack:** Spring MVC or WebFlux, matching packages and ApplicationContext type.
2. **State the need:** logging, HMAC verification, validation, single-pass parsing, or mandatory raw-byte replay?
3. **Choose the right extension point:** Servlet Filter, RequestBodyAdvice, or WebFilter/ServerHttpRequestDecorator.
4. **Scope tightly:** paths, methods, content types; avoid intercepting multipart uploads or unbounded streams.
5. **Enforce byte limits:** cover missing Content-Length, slow requests, and bodies > limit.
6. **Preserve exact bytes:** especially when HMAC depends on the original payload.
7. **Guarantee lifecycle safety:** Servlet sync/async contracts and Netty DataBuffer retain/release.
8. **Test both consumers:** verify the controller receives the right DTO after the Filter reads, not just the Filter in isolation.
9. **Test failure modes:** 400/413, malformed JSON, empty bodies, cancellation, concurrency, and Unicode.
10. **Monitor:** request latency, memory allocations, GC, 413 rates, and buffer-leak metrics/logs.

If you only need metadata auditing or DTO-level logic, eliminating the replay layer altogether is simpler, faster, and lower risk.

## 19. Official References

- [Spring Framework 6.2 – ContentCachingRequestWrapper](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html): caching read bytes, cache limits, and overflow hooks.
- [Spring Framework 6.2 – DataBufferUtils](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): join, maxByteCount, retain/release, error/cancellation.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled buffer lifecycle, doOnDiscard, and release.
- [Spring Framework – WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): codec memory limits and streaming.
- [Spring Framework 6.2 – ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): getBody and mutate/decorators.
- [Spring Boot 3.5 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html).
- [Spring Boot 3.5 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html).

**Conclusion:** A request body is a stream, not automatically rereadable. In MVC, ContentCachingRequestWrapper only suits observing already-read bytes; true replay requires a bounded HttpServletRequestWrapper providing fresh streams. In WebFlux, handle Flux<DataBuffer> inside a reactive pipeline managing release and cancellation, and supply a fresh body via ServerHttpRequestDecorator. Prefer single-pass parsing, buffer only when genuinely required, cap byte sizes, and test error, async, and resource-lifecycle paths.
