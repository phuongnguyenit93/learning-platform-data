# Reading the Request Body Once and Limits When Re-reading in a Filter

## 1. Why Does the Request Body Need Special Handling?

In Spring WebFlux, the request body is represented as a reactive data stream, usually **Flux<DataBuffer>** at the HTTP layer. Codecs can convert this byte stream into Java objects, for example:

~~~java
Mono<CreateOrderRequest> body =
        exchange.getRequest().getBody()
                .as(BodyExtractors.toMono(CreateOrderRequest.class));
~~~

The snippet above only illustrates the idea at the exchange layer; in a controller, the more familiar approach is using **@RequestBody Mono<CreateOrderRequest>**.

The important point: the request body comes from an HTTP connection being read as a stream. After one consumer reads all the data, the next consumer cannot by default ask the server to read again from the socket like reading a byte array in memory. **Treat a request's body as a one-shot data source** unless the application actively builds a cache/replay mechanism.

Example of a filter reading the body to verify a signature or validate JSON:

~~~java
return DataBufferUtils.join(exchange.getRequest().getBody())
        .flatMap(buffer -> {
            inspect(buffer);
            return chain.filter(exchange);
        });
~~~

The filter has already consumed the original body. If the controller behind it continues using @RequestBody, it may receive an empty body or have no data left to decode. Merely calling getBody() again or subscribing a second time does not make network content rewind back to the start automatically.

There are three common ways to handle this:

1. **Do not read the body in the filter:** prefer checking headers, method, path, or metadata if sufficient for the requirement.
2. **Read and process once:** the filter consumes the body, then passes the parsed result through ServerWebExchange attributes or a dedicated context; downstream does not read the body again.
3. **Bounded cache then replay:** the filter reads the original body once, copies it into a byte[], replaces the request with ServerHttpRequestDecorator, and emits a new DataBuffer each time downstream subscribes.

This lesson focuses on the third approach, when the filter is required to inspect the content yet the controller or handler still needs to read the body.

## 2. Components to Understand

### 2.1. ServerWebExchange and WebFilter

**ServerWebExchange** represents one HTTP exchange, providing the request, response, and request attributes. It can be mutated to use a different ServerHttpRequest:

~~~java
ServerWebExchange mutated =
        exchange.mutate()
                .request(decoratedRequest)
                .build();
~~~

This is how you replace the request for the next part of the filter chain. The new exchange still represents the same request/response lifecycle; it simply uses the provided request decorator.

**WebFilter** is the contract for chained request processing:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

The filter can inspect the request, replace the exchange and call chain.filter(mutatedExchange), or terminate early with an error response. It must return Mono<Void> so the framework coordinates the entire reactive process.

### 2.2. ServerHttpRequest and ServerHttpRequestDecorator

**ServerHttpRequest** provides the method, URI, headers, and body. The body is usually Flux<DataBuffer>.

**ServerHttpRequestDecorator** delegates most behavior to the original request while letting you override the method that needs changing, usually getBody():

~~~java
ServerHttpRequest decorated = new ServerHttpRequestDecorator(original) {
    @Override
    public Flux<DataBuffer> getBody() {
        // Emit the cached body.
    }
};
~~~

This is the appropriate extension point for downstream to receive cached data instead of the original body already consumed by the filter.

### 2.3. DataBuffer and DataBufferFactory

**DataBuffer** is Spring's byte buffer abstraction. Depending on the server, it may be backed by a heap buffer or a Netty pooled/direct buffer.

**DataBufferFactory** creates or wraps DataBuffers. The factory can be accessed from ServerHttpResponse:

~~~java
DataBuffer buffer =
        exchange.getResponse().bufferFactory().wrap(bytes);
~~~

The wrap(byte[]) method creates a DataBuffer backed by an existing byte array. In a decorator, create a new DataBuffer every time getBody() is subscribed so that each consumer has its own read position.

### 2.4. DataBufferUtils.join and Release

**DataBufferUtils.join(Publisher<DataBuffer>)** aggregates multiple buffers into one combined buffer. Overload with a limit:

~~~java
Mono<DataBuffer> joined =
        DataBufferUtils.join(request.getBody(), 64 * 1024);
~~~

The second parameter is the maximum number of bytes allowed to be aggregated. When the limit is exceeded, Spring emits **DataBufferLimitException**.

When join succeeds, the consumer receives the combined buffer and must release it after reading. If the source errors or is cancelled during aggregation, DataBufferUtils manages releasing the accumulated buffers according to the API contract. Do not hold pooled DataBuffers longer than necessary.

## 3. Cache and Replay Flow

A filter that caches the body with a limit follows this sequence:

~~~text
HTTP request body
       |
       v
Original Flux<DataBuffer>
       |
       v
DataBufferUtils.join(maxBytes)
       |
       +-- limit exceeded --> DataBufferLimitException --> HTTP 413
       |
       v
Read joined DataBuffer into byte[]
       |
       +--> release joined DataBuffer
       |
       v
Inspect content in filter
       |
       v
ServerHttpRequestDecorator
       |
       +--> getBody() subscription #1 -> new DataBuffer
       +--> getBody() subscription #2 -> new DataBuffer
       +--> getBody() subscription #n -> new DataBuffer
       |
       v
Controller / downstream codec reads body as normal
~~~

Principles:

- Subscribe to the original body only once to build the cache.
- Copy the content into byte[] before releasing the combined buffer.
- Do not return the same DataBuffer that has already been read or released.
- Each time downstream calls getBody(), it must receive a new DataBuffer with a fresh read position.
- Enforce the byte limit right at join; do not rely solely on Content-Length.
- If the filter does not need downstream to read again, there is no need to create a decorator.

## 4. Why Shouldn't You Cache the DataBuffer Itself?

An error-prone approach is keeping the combined buffer and re-emitting the same object:

~~~java
DataBuffer cached = ...;

@Override
public Flux<DataBuffer> getBody() {
    return Flux.just(cached);
}
~~~

This is unsafe if there are multiple subscriptions:

- The first consumer has already moved the buffer's read position.
- The next consumer may see no bytes left to read.
- If the buffer is pooled, releasing in the first consumer can make the buffer invalid.
- If reference counts are incremented without decrementing at the right time, the application can leak pooled memory.
- Two concurrent consumers can contend on the same buffer state.

A more controllable solution for small bodies is **copying to byte[] and then wrapping a new DataBuffer for each subscription**. The byte array must be treated as immutable throughout the replay lifecycle. Do not let downstream code mutate the array's contents.

## 5. Memory Limits: Content-Length Is Not Enough

### 5.1. Checking Content-Length Is Only an Early Optimization

You can reject early if the client declares a body larger than the limit:

~~~java
long contentLength = request.getHeaders().getContentLength();

if (contentLength > MAX_BODY_BYTES) {
    return payloadTooLarge(exchange);
}
~~~

However, Content-Length may be absent, especially when the request uses streaming or chunked transfer. A value of -1 means the total byte count is unknown in advance.

Therefore, checking the header does not replace the actual limit of DataBufferUtils.join:

~~~java
DataBufferUtils.join(request.getBody(), MAX_BODY_BYTES)
~~~

The limit at the join step is what protects against a body arriving in chunks without a reliable Content-Length.

### 5.2. Choosing a Limit by Request Type

Illustrative examples:

| Body type | Usually suitable strategy |
| --- | --- |
| Small JSON for create/update commands | Can cache with a limit of tens or hundreds of KiB |
| Large JSON | Consider single-pass processing or increasing the limit with control |
| File upload | Streaming, do not gather the whole file into byte[] |
| Multipart | Use multipart API or PartEvent streaming |
| SSE or streaming request | Process element by element; do not cache the entire stream |
| Unbounded or unknown-size body | Do not enable full replay; set clear limits and policies |

If each request caches up to 64 KiB and there are 1,000 concurrent requests, the byte[] part alone can take around 64 MiB, not counting buffers being joined, objects, and other overhead. During copying, both the joined DataBuffer and byte[] can coexist. Choose limits based on actual concurrency.

### 5.3. Codec Limit and Manual Cache Limit Are Two Different Things

Codec maxInMemorySize configuration controls certain decode/aggregate operations of message readers/writers. If a filter calls DataBufferUtils.join itself, the filter must pass maxByteCount itself.

Do not assume the codec limit automatically protects every manual snippet aggregating DataBuffers.

## 6. Handling DataBuffer with the Right Lifecycle

### 6.1. Release the Buffer After Copying

Basic pattern:

~~~java
byte[] copy(DataBuffer buffer) {
    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    } finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

After copying, byte[] is independent of the original pooled buffer. The finally block guarantees the combined buffer is released even if the copy operation throws an error.

### 6.2. Join Errors or Cancellation

DataBufferUtils.join is responsible for releasing accumulated buffers when the source emits an error or is cancelled according to the API contract. Do not release individual source buffers yourself before join completes, because join owns them during aggregation.

After join succeeds, the resulting buffer is the consumer's responsibility; release it after reading.

### 6.3. Discard and Intermediate Operators

If code keeps or drops DataBuffers through operators with discard support, consider doOnDiscard(DataBuffer.class, DataBufferUtils::release) at the right position. Do not add doOnDiscard mechanically to every pipeline; you must know which operator can drop elements and who owns the buffer.

### 6.4. Do Not Double-Release

Do not release a buffer already released by another consumer. Do not release the combined buffer before copying completes. Do not hold pooled buffers in a singleton field to reuse for later requests.

When unsure about ownership, read the contract of the API that creates or hands over the DataBuffer. Ownership and release timing must be clear.

## 7. Complete Filter Example: Caching JSON up to 64 KiB

The example below applies only to POST /api/echo with Content-Type application/json. The filter reads the body, confirms the JSON root is an object, and then replays the content so the controller can still use @RequestBody.

This is an example for Spring Boot 3.5.5 and Java 17+. In new projects, use a Spring Boot version approved by your organization and still maintained.

### 7.1. Project Structure

~~~text
request-body-cache/
├── pom.xml
└── src/
    ├── main/java/example/bodycache/
    │   ├── DemoApplication.java
    │   ├── RequestBodyCacheFilter.java
    │   └── EchoController.java
    └── test/java/example/bodycache/
        └── EchoControllerTest.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>request-body-cache</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 7.3. DemoApplication.java

~~~java
package example.bodycache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. RequestBodyCacheFilter.java

~~~java
package example.bodycache;

import java.io.IOException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestBodyCacheFilter implements WebFilter {

    static final int MAX_BODY_BYTES = 64 * 1024;
    static final String BODY_LENGTH_ATTRIBUTE =
            RequestBodyCacheFilter.class.getName() + ".bodyLength";

    private final ObjectMapper objectMapper;

    public RequestBodyCacheFilter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        ServerHttpRequest request = exchange.getRequest();
        MediaType contentType = request.getHeaders().getContentType();

        boolean targetRequest =
                HttpMethod.POST.equals(request.getMethod())
                && "/api/echo".equals(request.getURI().getPath())
                && contentType != null
                && MediaType.APPLICATION_JSON.isCompatibleWith(contentType);

        if (!targetRequest) {
            return chain.filter(exchange);
        }

        long contentLength = request.getHeaders().getContentLength();
        if (contentLength > MAX_BODY_BYTES) {
            return payloadTooLarge(exchange);
        }

        Mono<byte[]> cachedBody = DataBufferUtils
                .join(request.getBody(), MAX_BODY_BYTES)
                .map(this::copyAndRelease)
                .defaultIfEmpty(new byte[0])
                .onErrorMap(
                        DataBufferLimitException.class,
                        RequestBodyTooLargeException::new
                );

        return cachedBody
                .flatMap(bytes -> {
                    try {
                        JsonNode json = objectMapper.readTree(bytes);
                        if (json == null || !json.isObject()) {
                            return badRequest(exchange);
                        }
                    } catch (IOException error) {
                        return badRequest(exchange);
                    }

                    ServerHttpRequest decorated =
                            new ServerHttpRequestDecorator(request) {
                        @Override
                        public Flux<DataBuffer> getBody() {
                            return Flux.defer(() -> Flux.just(
                                    exchange.getResponse()
                                            .bufferFactory()
                                            .wrap(bytes)
                            ));
                        }
                    };

                    ServerWebExchange mutated = exchange.mutate()
                            .request(decorated)
                            .build();

                    mutated.getAttributes().put(
                            BODY_LENGTH_ATTRIBUTE,
                            bytes.length
                    );

                    // The filter can inspect the cached bytes here.
                    // The downstream controller still receives a replay.
                    return chain.filter(mutated);
                })
                .onErrorResume(
                        RequestBodyTooLargeException.class,
                        error -> payloadTooLarge(exchange)
                );
    }

    private byte[] copyAndRelease(DataBuffer buffer) {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return bytes;
        } finally {
            DataBufferUtils.release(buffer);
        }
    }

    private Mono<Void> badRequest(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
        return exchange.getResponse().setComplete();
    }

    private Mono<Void> payloadTooLarge(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.PAYLOAD_TOO_LARGE);
        return exchange.getResponse().setComplete();
    }

    private static final class RequestBodyTooLargeException
            extends RuntimeException {
        RequestBodyTooLargeException(Throwable cause) {
            super(cause);
        }
    }
}
~~~

Important points in the code:

- The filter only runs for the selected method, path, and media type.
- Content-Length larger than the limit is rejected early.
- If Content-Length is missing or does not reflect the real size, join still enforces MAX_BODY_BYTES.
- DataBufferLimitException from the join step is converted into a private exception so only the body-caching branch translates to HTTP 413.
- JSON is checked before calling the filter chain.
- The joined DataBuffer is copied and released in finally.
- The decorator uses Flux.defer to create a new DataBuffer on each subscription.
- byte[] is held in the decorator's closure for that specific request, not in a shared field of the singleton filter.

### 7.5. EchoController.java

~~~java
package example.bodycache;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, Object>> echo(
            @RequestBody Mono<Map<String, Object>> body,
            ServerWebExchange exchange) {

        return body.map(value -> {
            Map<String, Object> response = new LinkedHashMap<>();
            response.put("received", value);
            response.put(
                    "cachedBytes",
                    exchange.getAttributeOrDefault(
                            RequestBodyCacheFilter.BODY_LENGTH_ATTRIBUTE,
                            -1
                    )
            );
            return response;
        });
    }
}
~~~

The controller still uses @RequestBody as usual. It does not know the filter read the body earlier; ServerHttpRequestDecorator replays the cached bytes so the controller's codec can decode the JSON.

### 7.6. Running the Application

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Send a small JSON payload:

~~~powershell
curl.exe -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -H "Accept: application/json" --data-binary '{"name":"Ada"}'
~~~

Illustrative response body:

~~~json
{
  "received": {
    "name": "Ada"
  },
  "cachedBytes": 14
}
~~~

14 is the number of bytes in the UTF-8 JSON string without whitespace: {"name":"Ada"}. The controller receives the JSON even though the filter already read and parsed the body earlier.

If a body larger than 64 KiB is sent, the filter returns HTTP **413 Payload Too Large** before the controller is called. If the body is not a valid JSON object, the filter returns HTTP **400 Bad Request**.

## 8. Testing with WebTestClient

File **EchoControllerTest.java**:

~~~java
package example.bodycache;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class EchoControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void filterCanReadBodyAndControllerCanDecodeItAgain() {
        webTestClient.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("name", "Ada"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.received.name").isEqualTo("Ada")
                .jsonPath("$.cachedBytes").isNumber();
    }

    @Test
    void rejectsBodyLargerThanConfiguredLimit() {
        byte[] oversized =
                new byte[RequestBodyCacheFilter.MAX_BODY_BYTES + 1];

        webTestClient.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(oversized)
                .exchange()
                .expectStatus()
                .isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The first test confirms two things in the same request: the filter can read the body and the controller can still decode the replayed body. The second test confirms a body exceeding the limit is rejected.

This is an integration test with an embedded server, not a test calling the filter manually. It helps catch errors at the boundary between WebFilter, request decorator, codec, and controller.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Filter reads the original body and then calls chain with the old exchange | The downstream controller may receive an empty body | Cache bytes and replace the request with a decorator |
| Subscribing to the body twice and expecting data to replay automatically | Network source does not rewind automatically | Read the original source only once; replay explicitly |
| Reusing the same DataBuffer for multiple subscriptions | Read position or reference count has changed | Create a new DataBuffer from byte[] for each subscription |
| Keeping a pooled DataBuffer in a singleton field | Use-after-release or native memory leak | Copy byte[] and release the buffer at the right time |
| Calling DataBufferUtils.join without a limit | Client can send a huge body | Use join(publisher, maxByteCount) |
| Checking only Content-Length | Misses chunked bodies or bodies without length | Check the header early and always enforce a limit at join |
| Placing the filter after another filter that already read the body | The caching filter receives an already consumed body | Order the filter before the first consumer |
| Placing switchIfEmpty after chain.filter(...) | Mono<Void> completes empty and may call the chain twice | Handle empty body before calling the chain or use a sentinel |
| Globally caching every request | Unnecessary memory and latency increase | Cache only the routes, methods, and media types that truly need it |
| Caching multipart/file uploads in full | Easily exhausts heap and breaks streaming | Use PartEvent/streaming; consume/relay/release properly |
| Logging the raw request body | Leaks passwords, tokens, personal data | Log filtered metadata; store content only with a clear policy |
| Changing the body while keeping the old Content-Length | Client/server reads the wrong length | Update or remove Content-Length when the body changes |
| Catching DataBufferLimitException too broadly | May turn downstream errors into body-cache errors | Scope error handling around the join operation |
| Using byte[] caching unbounded by concurrency | Many concurrent requests pressure the heap | Limit body size, concurrency, and cache retention time |

### 9.1. The switchIfEmpty Trap with Mono<Void>

The following snippet can call the filter chain twice:

~~~java
return readBody()
        .flatMap(body -> chain.filter(exchange))
        .switchIfEmpty(chain.filter(exchange));
~~~

Reason: chain.filter returns Mono<Void>. Mono<Void> emits no onNext value; when it completes normally it is still empty in terms of data. Therefore switchIfEmpty can run the fallback branch after the first chain has finished processing.

The safe way is to handle the empty-body case **before** calling the chain:

~~~java
Mono<byte[]> bytes = readBody()
        .defaultIfEmpty(new byte[0]);

return bytes.flatMap(body -> {
    ServerWebExchange replayed = decorate(exchange, body);
    return chain.filter(replayed);
});
~~~

Or if you need to branch on empty/non-empty, convert the read result into a type with a distinguishing value before flatMapping to Mono<Void>. Do not place switchIfEmpty directly after chain.filter if the goal is a fallback for an empty body.

## 10. When Should You Use Exchange Attributes Instead of Replay?

If the filter only needs to parse once and the downstream handler does not need to read the original body, there is no need to create a request decorator.

Example:

1. The filter reads the body once.
2. Decodes it into a JsonNode or a small DTO.
3. Checks the policy.
4. Stores the verified result in exchange attributes.
5. The handler reads the DTO/metadata from the exchange instead of parsing the body again.

This avoids a second decode and avoids replaying bytes. However, it requires downstream to be designed to accept pre-parsed data; a controller with @RequestBody still needs the body.

| Situation | Choice |
| --- | --- |
| Filter verifies a signature and controller still needs @RequestBody | Cache bytes and replay |
| Filter parses body, handler directly uses the parsed DTO | Store DTO/metadata in exchange attributes |
| Handler is a functional endpoint and can receive a processed ServerRequest | Design handler to read prepared metadata/context |
| Large body or unbounded stream | Do not cache in full; process streaming |
| Only need to check headers or content type | Do not read the body in the filter |

Do not store the raw body in a singleton field. Exchange attributes are request-scoped, whereas fields of a filter bean are usually shared across multiple concurrent requests.

## 11. Multipart and Streaming: Do Not Gather the Entire Body

For file uploads or multipart requests, the body can be very large. You should not call join to gather everything into one byte[] just to read it again.

Spring WebFlux provides multipart handling per PartEvent:

~~~java
request.bodyToFlux(PartEvent.class)
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
                partEvents.switchOnFirst((signal, events) -> {
                    if (!signal.hasValue()) {
                        return events.then();
                    }

                    PartEvent event = signal.get();

                    if (event instanceof FormPartEvent form) {
                        processField(form.name(), form.value());
                        return events.then();
                    }

                    if (event instanceof FilePartEvent file) {
                        return events
                                .map(PartEvent::content)
                                .concatMap(this::writeChunk);
                    }

                    return Mono.error(
                            new IllegalStateException("Unsupported part")
                    );
                })
        );
~~~

This is an illustrative streaming snippet, requiring the application's processField and writeChunk methods. For each PartEvent, the DataBuffer content must be **completely consumed, relayed, or released**. Do not skip file buffers if you want to avoid resource leaks.

If the filter only needs to inspect the filename, content type, or multipart metadata, consider processing events as a stream and passing the needed metadata. Avoid caching entire file uploads just so downstream can read them again.

## 12. Filter Order and Coordinating with Spring Security

A body-caching filter must run **before any other filter that may consume the request body**. For example:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class RequestBodyCacheFilter implements WebFilter {
    // ...
}
~~~

This is an ordering suggestion, not a substitute for reviewing the application's actual filter order. If Spring Security, a gateway filter, or a custom filter reads the body first, a caching filter placed afterward will no longer receive the original body.

You should not cache every request for logging purposes when there is no business need. Security filters should avoid logging passwords, access tokens, refresh tokens, payment information, or personal data. If auditing is needed, store filtered metadata, request IDs, or authentication results; do not store raw payloads by default.

## 13. Limits and Modifying the Body

In the example, byte[] is replayed unchanged so the original Content-Length remains accurate. If the filter transforms the content:

- Update Content-Length to the new byte count, or remove the header so the runtime handles it with the appropriate mechanism.
- Ensure Content-Type reflects the transformed body.
- Do not keep old Transfer-Encoding or Content-Encoding if the content changed and the semantics are no longer valid.
- If signing or verifying signatures, clearly define which byte representation is signed: raw bytes, canonical JSON, or content after decompression.
- Do not decode to String and re-encode if the signature depends on exact bytes, because encoding, whitespace, or field order can differ.

Cache/replay only solves making downstream receive the bytes again. It does not automatically guarantee the content is canonicalized, validated, or business-safe.

## 14. Testing and Observability in Production

### 14.1. Cases to Test

- Small JSON body: filter can read it and controller can still decode it.
- Empty body: handled per endpoint contract, without calling the chain twice.
- Malformed JSON: returns an appropriate error before the controller processes it.
- Oversized body with known Content-Length.
- Oversized body sent as chunked/without known length.
- Request method/path/content type outside the cache scope: filter skips.
- Downstream subscribes to the body as needed: each subscription receives a new buffer.
- Cancellation or error during join: accumulated buffers are released per contract.
- Multipart/upload: does not gather the whole file into memory.
- Many concurrent requests: heap and pooled memory remain within limits.

### 14.2. Metrics to Monitor

- Number of cached requests and skipped requests.
- Number of bodies rejected for exceeding the limit.
- Average and high-percentile body sizes.
- Time spent joining/parsing in the filter.
- Number of requests holding byte[] caches concurrently.
- Heap usage, GC pauses, and Netty pooled buffer leak warnings.
- Rates of decode errors, 400, 413, and cancellation.

Do not use raw bodies, user IDs, or tokens as high-cardinality metric labels or log data.

## 15. Key Takeaways

- An HTTP request body is a stream; treat the original body source as one-shot.
- A filter that reads the body before the controller will consume data the controller may need.
- For downstream to read again, cache with a limit and then use ServerHttpRequestDecorator.
- Use DataBufferUtils.join with maxByteCount; Content-Length is only an early check.
- Copy the data into byte[] and then release the combined DataBuffer in finally.
- Create a new DataBuffer for each subscription using DataBufferFactory.wrap(bytes) inside Flux.defer.
- Do not replay the same pooled DataBuffer that has already been read or released.
- Handle DataBufferLimitException within a tight scope to return a clear 413.
- Place the filter before all other body consumers and cache only the needed routes.
- Multipart and streaming should be processed part by part; consume, relay, or release every DataBuffer.
- If downstream can use the parsed result in exchange attributes, there is no need to replay the body.
- Test small bodies, empty bodies, oversized bodies, parse errors, and cancellation.

**Official documentation:**
- [Spring Framework — Data Buffers and Codecs: pooled buffers, release and DataBufferUtils.join](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Functional Endpoints: request body streams and PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework Javadoc — ServerHttpRequestDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequestDecorator.html)
- [Spring Framework Javadoc — WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework Javadoc — ServerWebExchange.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.Builder.html)
