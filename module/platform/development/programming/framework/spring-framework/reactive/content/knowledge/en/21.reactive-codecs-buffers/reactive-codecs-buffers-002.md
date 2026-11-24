# ServerCodecConfigurer, ClientCodecConfigurer, and ExchangeStrategies in Spring WebFlux

## 1. Objectives

Spring WebFlux needs to convert data between HTTP and the Java types used by the application. When a client sends JSON, form, or multipart data, the server must read bytes from the request and create objects. When a controller returns an object, the server must serialize the object into a response body. On the client side, WebClient also needs to encode request bodies and decode response bodies.

**Codecs** are the components that perform data conversion. Spring provides default codecs and configuration APIs so applications can add or replace them:

- **ServerCodecConfigurer:** configures HTTP message readers/writers on the WebFlux server side.
- **ClientCodecConfigurer:** configures HTTP message readers/writers on the HTTP client side.
- **ExchangeStrategies:** the set of HTTP reading/writing strategies used by WebClient via ExchangeFunction; it holds the configured list of readers/writers.

The three components are related but not interchangeable. ServerCodecConfigurer is for the server; ClientCodecConfigurer is for the client; ExchangeStrategies is the object encapsulating codec configuration on the WebClient side.

This lesson walks through the read/write flow, the role of each API, how to customize default codecs, register custom codecs, configure memory limits, and manage DataBuffer. Examples use Java 17+ and common APIs from Spring Framework 6.2/7.0.

## 2. Codec, Encoder, Decoder, HttpMessageReader, and HttpMessageWriter

The abstractions span multiple layers:

| Component | Responsibility | Input | Output |
| --- | --- | --- | --- |
| Encoder | Encodes objects into byte buffers | Publisher of objects | Publisher of DataBuffer |
| Decoder | Decodes byte buffers into objects | Publisher of DataBuffer | Publisher of objects |
| HttpMessageReader | Reads HTTP content into Java types | HTTP body, headers, target type | Publisher of objects |
| HttpMessageWriter | Writes Java types as HTTP content | Publisher of objects, headers | HTTP body |
| CodecConfigurer | Registers default and custom readers/writers | Codec configuration | List of readers/writers |
| ExchangeStrategies | Encapsulates readers/writers for WebClient | Client codec configuration | Strategy used by ExchangeFunction |

Encoder/Decoder are HTTP-independent data conversion abstractions. HttpMessageReader/HttpMessageWriter add HTTP context such as Content-Type, MediaType, ResolvableType, headers, and body writing behavior. In many cases, Spring wraps an Encoder with EncoderHttpMessageWriter and a Decoder with DecoderHttpMessageReader for use in WebFlux.

Example request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"id":"o-42","quantity":3}
```

Server-side processing flow:

1. WebFlux selects an HttpMessageReader compatible with the Content-Type and the controller parameter type.
2. The Reader reads DataBuffers from the HTTP body.
3. The Decoder, such as the Jackson JSON decoder, converts bytes into Java objects.
4. The controller processes the object and returns a Mono or Flux.
5. WebFlux selects an HttpMessageWriter compatible with the return type and response media type.
6. The Encoder converts the object into DataBuffers.
7. The server writes the buffers to the HTTP response in a non-blocking manner.

On the client side, WebClient performs the reverse direction: the encoder writes the request body; the decoder reads the response body.

## 3. Default Codecs in Spring WebFlux

Spring provides core codecs in spring-core and HTTP codecs in spring-web. Which specific codecs are registered depends on the libraries present on the classpath.

Commonly supported groups:

| Data | Typical codec/reader/writer | Notes |
| --- | --- | --- |
| String / CharSequence | StringEncoder, StringDecoder, CharSequenceEncoder | Text and character sequences |
| byte[] | ByteArrayEncoder, ByteArrayDecoder | Binary data aggregated into an array |
| ByteBuffer | ByteBufferEncoder, ByteBufferDecoder | Interoperation with Java NIO |
| DataBuffer | DataBufferEncoder, DataBufferDecoder | Working directly with buffers |
| Resource | ResourceHttpMessageReader/Writer | Reading/writing files or resources |
| JSON | Jackson JSON encoder/decoder | Available when a compatible Jackson version is present |
| Smile | Jackson Smile encoder/decoder | Jackson's binary JSON format |
| XML | JAXB2 or compatible codec | Depends on JAXB library |
| Protocol Buffers | Protobuf encoder/decoder | Depends on protobuf-java |
| Form URL encoded | FormHttpMessageReader/Writer | application/x-www-form-urlencoded |
| Multipart | MultipartHttpMessageReader/Writer | multipart/form-data and related forms |
| Server-Sent Events | SSE reader/writer | text/event-stream |

Not every codec is always present. For example, the Protobuf codec requires the Protobuf library; the JSON codec requires Jackson or a compatible JSON library. Spring Boot also adjusts codecs according to the classpath and the application's Jackson configuration.

### 3.1. Jackson and JSON

The Jackson decoder uses a non-blocking parser to read the byte stream and construct objects. For a single JSON object, the decoder produces one object. For a multi-value publisher, the decoder can emit each object once enough bytes have been received to complete that object, depending on the streaming format.

On the encoding side:

- With a Mono<T>, the encoder serializes one object.
- With Flux<T> and media type application/json, elements are collected into a list by default and serialized as a JSON array.
- With streaming media types such as application/x-ndjson, the encoder can encode, write, and flush each element line by line.
- With Server-Sent Events, the JSON encoder is invoked per event and the output is flushed so events are delivered promptly.

An easy-to-miss detail: the Jackson JSON encoder/decoder does not treat String as a normal JSON object by default. Spring typically treats String or character sequences as already-serialized JSON content and uses the CharSequence codec. If you need to return a JSON array from a Flux<String>, call collectList and encode Mono<List<String>>.

Example:

```java
@GetMapping(value = "/names", produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<List<String>> names() {
    return Flux.just("An", "Binh", "Chi")
            .collectList();
}
```

JSON response:

```json
["An","Binh","Chi"]
```

If returning Flux<String> directly with application/json, do not assume Spring will produce a JSON array of strings. Choose a body type and media type that accurately express the contract.

### 3.2. JSON Streaming and NDJSON

If you want to emit multiple objects line by line, use the application/x-ndjson media type:

```java
@GetMapping(
        value = "/events",
        produces = "application/x-ndjson")
public Flux<OrderEvent> events() {
    return Flux.just(
            new OrderEvent("o-1", "CREATED"),
            new OrderEvent("o-2", "PAID"),
            new OrderEvent("o-3", "SHIPPED"));
}
```

Data is encoded as individual JSON objects, each on its own line:

```text
{"orderId":"o-1","status":"CREATED"}
{"orderId":"o-2","status":"PAID"}
{"orderId":"o-3","status":"SHIPPED"}
```

NDJSON fits per-record processing and backpressure. Using application/json for a Flux collects elements into a collection by default; using a streaming media type allows elements to be written incrementally.

## 4. ServerCodecConfigurer: Server-Side Codec Configuration

ServerCodecConfigurer provides the default readers/writers for the WebFlux server. It is used in annotated controllers, functional endpoints, and form/multipart reading utilities via ServerWebExchange.

The common way to extend it is to implement WebFluxConfigurer and override configureHttpMessageCodecs:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ServerCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024);
    }
}
```

This configuration sets the buffering limit for default codecs to 1 MiB. This is a server configuration example; you do not need to create ServerCodecConfigurer manually in a normal WebFlux application because the framework manages it.

### 4.1. defaultCodecs and customCodecs

CodecConfigurer has two main API groups:

- `defaultCodecs()`: customize or replace codecs registered by Spring by default.
- `customCodecs()`: add new HttpMessageReader or HttpMessageWriter instances.

Example of changing the memory limit:

```java
configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
```

Example of registering custom readers/writers:

```java
configurer.customCodecs().register(myDecoder);
configurer.customCodecs().register(myEncoder);
```

Here myDecoder must implement an appropriate Decoder or HttpMessageReader; myEncoder must implement an appropriate Encoder or HttpMessageWriter. This is an extension point, not a built-in Spring class.

If a custom codec needs to receive default settings such as buffering limits or logging policies, you can use:

```java
configurer.customCodecs()
        .registerWithDefaultConfig(myDecoder);
```

registerWithDefaultConfig allows the custom codec to receive the corresponding default configuration values. With plain register, a custom codec may have to manage limits or options that default codecs already support on its own.

### 4.2. Do Not Disable Default Codecs Arbitrarily

You can call:

```java
configurer.registerDefaults(false);
```

This disables registering default readers/writers. When doing so, the application must provide all required codecs itself via customCodecs. If you forget to register JSON, String, byte[], form, or multipart readers/writers, endpoints that previously worked may fail to read/write bodies.

Only disable defaults when you truly want control over the entire codec list, understand which codecs each endpoint depends on, and have test coverage. In normal applications, keeping defaults and adding/customizing is the safer choice.

### 4.3. Configuring Jackson

Spring Boot applies the application's Jackson properties to the corresponding codecs. If deeper customization is needed, you can use a Jackson-specific builder or replace the default codecs with an encoder/decoder using a custom ObjectMapper.

The example below is for applications using Jackson 2.x:

```java
ObjectMapper mapper = Jackson2ObjectMapperBuilder.json()
        .modulesToInstall(new JavaTimeModule())
        .featuresToDisable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

configurer.defaultCodecs().jackson2JsonDecoder(
        new Jackson2JsonDecoder(mapper));

configurer.defaultCodecs().jackson2JsonEncoder(
        new Jackson2JsonEncoder(mapper));
```

Corresponding Jackson and Spring imports are required, including Jackson2ObjectMapperBuilder, Jackson2JsonDecoder, Jackson2JsonEncoder, ObjectMapper, JavaTimeModule, and DeserializationFeature. This snippet illustrates replacing the default Jackson 2 codecs.

**Version note:** Spring Framework 6.x typically uses the Jackson2JsonEncoder/Decoder classes when the application uses Jackson 2. Spring Framework 7 also supports the Jackson 3 generation with the JacksonJsonEncoder/Decoder classes. Choose codecs matching your actual Jackson dependency and Spring Boot BOM; do not arbitrarily mix Jackson 2 and Jackson 3.

### 4.4. Spring Boot and @EnableWebFlux

When using Spring Boot, you normally only need to declare @Configuration implements WebFluxConfigurer. Do not add @EnableWebFlux if you want Spring Boot to keep its WebFlux auto-configuration customizations.

@EnableWebFlux is appropriate when you want framework-level control over WebFlux configuration and accept replacing part of Boot's auto-configuration. Adding this annotation just to change maxInMemorySize is usually unnecessary.

Spring Boot also provides CodecCustomizer and codec configuration properties. Property names and the CodecCustomizer package may vary across Boot generations; consult documentation for the exact version in use. If you already have a WebFluxConfigurer, avoid creating multiple conflicting configurations that modify the same codec without understanding application order.

## 5. ClientCodecConfigurer: Client-Side Codec Configuration

ClientCodecConfigurer is the CodecConfigurer for HTTP clients. It provides default readers/writers and client-specific options, including multipart support and the SSE decoder.

You usually do not need to create ClientCodecConfigurer manually. WebClient.Builder provides the codecs callback to adjust configuration:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.test")
        .codecs(configurer -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(2 * 1024 * 1024);
        })
        .build();
```

This is a concise way to increase the buffering limit for WebClient's default codecs to 2 MiB.

Client-side customizations affect:

- Request bodies that WebClient encodes before sending.
- Response bodies that WebClient decodes after receiving.
- The client's multipart reader/writer.
- The client's SSE decoder.
- Buffering limits and logging options of default codecs.

ServerCodecConfigurer does not automatically configure WebClient. If an application both runs a WebFlux server and calls external services via WebClient, configure codecs explicitly for each side.

## 6. ExchangeStrategies: WebClient's Codec Strategy Set

ExchangeStrategies is the object encapsulating the HttpMessageReader and HttpMessageWriter instances used by an ExchangeFunction. WebClient relies on ExchangeStrategies to encode requests and decode responses.

Important factories/builders:

| API | Purpose |
| --- | --- |
| `ExchangeStrategies.withDefaults()` | Obtain the default strategy |
| `ExchangeStrategies.builder()` | Create a builder pre-populated with default configuration to customize |
| `ExchangeStrategies.empty()` | Create an empty builder without registering defaults |
| `builder.codecs(...)` | Configure ClientCodecConfigurer inside the strategy |
| `builder.build()` | Build the ExchangeStrategies |
| `strategies.mutate()` | Create a new builder based on an existing strategy |

Example of creating a custom strategy:

```java
ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs(configurer -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(2 * 1024 * 1024);
        })
        .build();

WebClient client = WebClient.builder()
        .baseUrl("https://api.example.test")
        .exchangeStrategies(strategies)
        .build();
```

Here ExchangeStrategies contains the default codecs along with the new memory limit. WebClient uses that strategy for client requests/responses.

### 6.1. When to Use WebClient.Builder.codecs vs. ExchangeStrategies?

For most cases, prefer:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
        .build();
```

This approach lets other components contribute configuration to WebClient.Builder as well. It is usually clearer than creating a strategy manually and replacing everything.

Use ExchangeStrategies when:

- You want to create an independent, reusable strategy.
- You want to control the strategy at the ExchangeFunction level.
- You want to share the same reader/writer configuration across multiple WebClient instances.
- You want to clone or mutate an existing strategy.
- You need explicit control over the exact set of codecs used by the client.

Once built, WebClient is immutable. If you need a variant client, use client.mutate() to create a new builder retaining existing settings and adding filters or codecs. Never modify a built WebClient directly.

### 6.2. ClientCodecConfigurer Inside ExchangeStrategies

You can declare the ClientCodecConfigurer type explicitly so readers see the configuration boundary:

```java
ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs((ClientCodecConfigurer configurer) -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(1024 * 1024);
        })
        .build();
```

ClientCodecConfigurer provides defaultCodecs/customCodecs just like the general CodecConfigurer. The difference is that it adds codecs and options specific to the HTTP client.

### 6.3. Do Not Use ExchangeStrategies.empty() Unless Replacing Everything

ExchangeStrategies.empty() creates an empty configuration. If you use it and register only a JSON decoder, other default readers/writers may be missing: String, byte[], Resource, form, multipart, or SSE.

This is an option for systems requiring full codec control, not a shortcut to "create a lighter WebClient." Prefer builder() when you want to keep defaults and tweak a few options.

## 7. Customizing Codecs: Three Common Levels

### 7.1. Tuning Default Codecs

Use when you only need to adjust default codec behavior:

```java
configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
configurer.defaultCodecs().enableLoggingRequestDetails(false);
```

maxInMemorySize sets the buffering limit. enableLoggingRequestDetails controls detailed logging of form data and headers; caution is warranted by default because these data can contain secrets or personal information.

### 7.2. Replacing Default Codecs

Use when you need a JSON encoder/decoder with a custom ObjectMapper or JsonMapper. See the Jackson 2 example in section 4.3. When replacing encoder and decoder, replace both consistently if the same serialization rules must apply in both directions.

Avoid creating a new ObjectMapper missing modules and accidentally replacing default codecs. For example, missing the Java Time module can cause LocalDate/Instant types to serialize unexpectedly. Reuse the application's Jackson configuration or register the required modules.

### 7.3. Registering a Custom Encoder/Decoder

Use when a media type or wire format is not supported by default codecs, such as an application-specific binary format.

A custom decoder needs to:

1. Declare the Java types it can decode.
2. Declare the media types it supports.
3. Read DataBuffers in a non-blocking manner.
4. Handle data split across multiple buffers.
5. Release consumed or discarded buffers.
6. Handle errors and cancellation without retaining buffers.
7. Have tests for valid, incomplete, malformed, and multi-buffer payloads.

A custom encoder needs to:

1. Identify the object types and media types it can encode.
2. Convert objects into a DataBuffer or stream of buffers.
3. Release buffers if serialization fails before handing them off to the consumer.
4. Support backpressure, without buffering unbounded streams into memory.
5. Ensure consumers receive buffers with clear ownership.

Registering on the server:

```java
configurer.customCodecs()
        .registerWithDefaultConfig(new MyBinaryDecoder());
```

Registering on WebClient:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.customCodecs()
                        .registerWithDefaultConfig(new MyBinaryDecoder()))
        .build();
```

`MyBinaryDecoder` is a class implemented by the application. Both snippets are registration patterns, not standalone programs. If a custom codec manages its own limits or logging, configure them explicitly rather than assuming every default codec setting applies automatically.

## 8. maxInMemorySize and DataBufferLimitException

Spring limits the number of bytes decoders/readers are allowed to buffer in memory to prevent applications from buffering overly large payloads. The common codec default is **256 KiB**.

If data requiring buffering exceeds the limit, Spring may emit:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

This error commonly appears when:

- Reading an entire request body into a single object.
- Using `@RequestBody byte[]` or `String` for a large payload.
- Parsing URL-encoded form data.
- Reading a large multipart non-file part.
- Decoding an oversized JSON/NDJSON element.
- Using bodyToMono or a client API that aggregates the entire response.
- A custom decoder aggregates multiple DataBuffers into one object.

For certain streaming formats, the limit applies to the bytes of each object being split/aggregated, not necessarily the total size of the entire stream. Thus, a long Flux of many small elements can run well past 256 KiB in total without aggregating the whole stream into one buffer.

### 8.1. Increasing the Server-Side Limit

```java
@Configuration(proxyBeanMethods = false)
public class ServerCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(5 * 1024 * 1024);
    }
}
```

Example increasing the limit to 5 MiB. Choose values strictly based on valid API request sizes, concurrency, and memory budget. With many concurrent large requests, total memory pressure can be far larger than a single request's limit.

### 8.2. Increasing the WebClient Limit

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(5 * 1024 * 1024))
        .build();
```

The client-side limit is independent of the server. If the server accepts a 5 MiB body while WebClient only buffers 256 KiB, the client can still fail decoding a large response. Configure the side that is reading the data.

### 8.3. Do Not Raise the Limit to Mask Streaming Bugs

If data can be very large or unbounded, design for streaming instead of raising maxInMemorySize to a huge value.

Example:

```java
@GetMapping(
        value = "/export",
        produces = "application/x-ndjson")
public Flux<ExportRow> export() {
    return exportService.streamRows();
}
```

The Flux is written incrementally in NDJSON format. The client can use bodyToFlux(ExportRow.class) to process each line:

```java
return webClient.get()
        .uri("/export")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(ExportRow.class);
```

This reduces the need to buffer all data onto the heap. However, each element must still remain reasonably sized and decoder limits still matter.

## 9. DataBuffer and Memory Management

### 9.1. What Is DataBuffer?

DataBuffer is Spring's abstraction representing a byte region. It can wrap a byte array, ByteBuffer, or a server buffer such as Netty ByteBuf.

Related APIs:

- **DataBufferFactory:** allocates or wraps DataBuffers.
- **DataBuffer:** reads/writes bytes and manages read/write positions.
- **PooledDataBuffer:** a buffer that can be pooled and managed via reference counting.
- **DataBufferUtils:** utilities for join, retain, release, and skip/take by byte count.

WebFlux typically obtains DataBufferFactory from ServerHttpResponse or ClientHttpRequest. Applications do not need to create factories manually in typical controller cases.

### 9.2. Why Do Pooled Buffers Need to Be Released?

Some servers such as Reactor Netty use pooled/direct buffers to reduce allocations and copying. PooledDataBuffer has a reference count:

- On creation, the reference count typically starts at 1.
- retain increments the reference count.
- release decrements the reference count.
- When the reference count reaches 0, the memory region can be returned to the pool.

If an application holds buffers without releasing them promptly, native/direct memory can remain pinned and cause a memory leak. If released too early or multiple times, other code may read a buffer already returned to the pool, producing hard-to-diagnose errors.

In most controllers, use Java objects and default codecs so Spring manages buffers. You only need manual management when consuming/producing DataBuffers directly or writing a custom codec.

### 9.3. Releasing Consumed Buffers

If a custom decoder finishes reading a DataBuffer and does not retain it, it can use:

```java
DataBufferUtils.release(dataBuffer);
```

Do not release a buffer you do not own or a buffer already handed over to another component responsible for it. Ownership must be clear at every step.

### 9.4. Buffers Discarded by Operators

A decoder may use operators such as filter, skip, flatMap, reduce, or prefetch. Some buffers may be dropped on filter, error, or cancellation. In such cases, register cleanup for discarded buffers:

```java
return buffers
        .filter(this::isRelevant)
        .map(this::decode)
        .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release);
```

This is a conceptual example for a custom decoder; ensure the operator chain and buffer ownership align. doOnDiscard does not replace releasing buffers already read successfully by the decoder or buffers held in internal state.

### 9.5. Holding Buffers Across Multiple Steps

If a decoder temporarily stores one or more DataBuffers, it must release them when:

- Reading completes.
- An error occurs before reading finishes.
- The publisher is cancelled.
- Buffers are dropped due to filter/skip or other operators.

Do not implement only the happy path. Leaks often occur along error/cancel paths, especially when clients disconnect mid-upload/download.

### 9.6. DataBufferUtils.join

DataBufferUtils.join can combine a publisher of multiple DataBuffers into a single DataBuffer, potentially using a composite buffer if supported by the implementation. This utility API is safer than manually copying bytes from each buffer into an array.

```java
Mono<DataBuffer> joined = DataBufferUtils.join(buffers);
```

join can still aggregate a large amount of data. Use it when payloads have clear bounds and an appropriate max-bytes policy; do not use it to aggregate an unbounded stream.

### 9.7. Encoders and Buffer Ownership

An Encoder creates DataBuffers for a consumer to read. In WebFlux, the consumer is typically a writer writing to the HTTP response or client request; the writer is responsible for releasing received buffers. The encoder must release a buffer if serialization fails while writing data into it before returning it to the consumer.

Do not release a buffer immediately after emitting it to the response writer, because the writer still needs to read its content. Conversely, if the encoder allocates a buffer and throws an exception before emitting, the encoder must clean up its own buffer.

## 10. Multipart and Related Limits

Multipart has additional limits beyond maxInMemorySize:

| Limit | Effect |
| --- | --- |
| maxInMemorySize | For non-file parts, limits bytes kept in memory; for file parts, determines the threshold to spill to disk |
| maxDiskUsagePerPart | Limits disk space written per file part |
| maxParts | Limits total number of multipart parts |

To configure these multipart limits, you typically provide a pre-configured MultipartHttpMessageReader to ServerCodecConfigurer. Do not simply raise maxInMemorySize if your goal is limiting file disk usage or part counts.

WebFlux can read multipart in a map-like form via MultiValueMap<String, Part>. This is convenient when accessing multiple parts by name, but requires parsing and collecting the multipart structure.

If large uploads must be processed via streaming, you can use Flux<PartEvent> via @RequestBody instead of requiring the entire multipart request to be collected into a map. When processing individual events/parts, manage DataBuffers and clean up according to ownership.

## 11. Logging Request Details and Sensitive Data

Default codecs support enabling detailed request data logging:

```java
configurer.defaultCodecs()
        .enableLoggingRequestDetails(true);
```

On the WebClient side:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .enableLoggingRequestDetails(true))
        .build();
```

This option can cause form data or headers to be logged in more detail. By default, Spring masks certain sensitive data. Enabling request detail logging can expose Authorization headers, cookies, form fields, personal information, or confidential payloads.

Enable it only temporarily when debugging in a controlled environment; disable it after investigation. Production should use selective logging, redact data, and avoid logging entire request/response bodies.

## 12. Spring Boot WebFlux Example: Server and Client Configuration

The example below uses Java 17+, Spring Boot 3.x, and Spring Framework 6.2 with default Jackson 2. It demonstrates server configuration, a JSON controller, WebClient using ExchangeStrategies, and HTTP tests with WebTestClient.

### 12.1. Dependencies

In build.gradle, the project requires the core dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

The project requires a compatible Spring Boot Gradle plugin and dependency management. Use Boot's BOM to manage Spring Framework, Reactor, Jackson, and test library versions; do not override spring-webflux separately.

### 12.2. Application Class

File src/main/java/demo/CodecDemoApplication.java:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}
```

### 12.3. ServerCodecConfigurer

File src/main/java/demo/ServerCodecConfiguration.java:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ServerCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024);
    }
}
```

The server retains default codecs and raises the buffering limit to 1 MiB. In Spring Boot, do not add @EnableWebFlux for this example.

### 12.4. Request/Response DTOs

File src/main/java/demo/EchoRequest.java:

```java
package demo;

public record EchoRequest(String message) {
}
```

File src/main/java/demo/EchoResponse.java:

```java
package demo;

public record EchoResponse(String message, int length) {
}
```

### 12.5. Controller

File src/main/java/demo/EchoController.java:

```java
package demo;

import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @PostMapping(
            value = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<EchoResponse> echo(
            @RequestBody Mono<EchoRequest> request) {

        return request.map(body ->
                new EchoResponse(
                        body.message(),
                        body.message().length()));
    }

    @GetMapping(
            value = "/api/events",
            produces = "application/x-ndjson")
    public Flux<EchoResponse> events() {
        return Flux.fromIterable(List.of(
                new EchoResponse("created", 7),
                new EchoResponse("updated", 7),
                new EchoResponse("closed", 6)));
    }
}
```

The POST endpoint receives JSON via the decoder and returns JSON via the encoder. The GET endpoint returns Flux as NDJSON so each object can be written on its own line rather than collected into a JSON array.

### 12.6. ClientCodecConfigurer and ExchangeStrategies

File src/main/java/demo/ClientCodecConfiguration.java:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ClientCodecConfiguration {

    @Bean
    WebClient echoWebClient() {
        ExchangeStrategies strategies = ExchangeStrategies.builder()
                .codecs(configurer ->
                        configurer.defaultCodecs()
                                .maxInMemorySize(1024 * 1024))
                .build();

        return WebClient.builder()
                .baseUrl("http://localhost:8080")
                .exchangeStrategies(strategies)
                .build();
    }
}
```

ExchangeStrategies is created from the default builder, so default codecs remain present. The client only changes the buffering limit. Once built, WebClient is immutable.

If you only need quick configuration, you can omit ExchangeStrategies and use WebClient.Builder.codecs:

```java
WebClient client = WebClient.builder()
        .baseUrl("http://localhost:8080")
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(1024 * 1024))
        .build();
```

Both approaches customize ClientCodecConfigurer inside WebClient. Using ExchangeStrategies is useful when you need to keep the strategy as a reusable object.

### 12.7. Service Calling WebClient

File src/main/java/demo/EchoClient.java:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoClient {

    private final WebClient client;

    public EchoClient(WebClient echoWebClient) {
        this.client = echoWebClient;
    }

    public Mono<EchoResponse> send(EchoRequest request) {
        return client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .bodyToMono(EchoResponse.class);
    }

    public Flux<EchoResponse> events() {
        return client.get()
                .uri("/api/events")
                .accept(MediaType.parseMediaType("application/x-ndjson"))
                .retrieve()
                .bodyToFlux(EchoResponse.class);
    }
}
```

The client uses the encoder to serialize EchoRequest into JSON, then the decoder creates EchoResponse from JSON. With NDJSON, bodyToFlux decodes each object as a stream.

The service does not call block() or subscribe(); publishers are returned so the caller decides how to compose them and manage lifecycle.

### 12.8. Testing with WebTestClient

File src/test/java/demo/EchoControllerTest.java:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class EchoControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void decodesAndEncodesJson() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("hello"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello")
                .jsonPath("$.length").isEqualTo(5);
    }

    @Test
    void writesNdjsonStream() {
        client.get()
                .uri("/api/events")
                .accept(MediaType.parseMediaType("application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.parseMediaType("application/x-ndjson"))
                .expectBody()
                .jsonPath("$[0].message").isEqualTo("created")
                .jsonPath("$[1].message").isEqualTo("updated")
                .jsonPath("$[2].message").isEqualTo("closed");
    }
}
```

The first test confirms that the server's JSON reader and writer work. The second test confirms the NDJSON media type and element contents. Tests can be adjusted to match the Spring Boot/test support version in the project.

Run tests:

```bash
./gradlew test
```

### 12.9. Running and Calling with curl

Start:

```bash
./gradlew bootRun
```

Send JSON:

```bash
curl -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -H "Accept: application/json" -d "{"message":"hello"}"
```

Expected JSON body:

```json
{
  "message": "hello",
  "length": 5
}
```

Call stream:

```bash
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/api/events
```

NDJSON output:

```text
{"message":"created","length":7}
{"message":"updated","length":7}
{"message":"closed","length":6}
```

JSON field order depends on serializer configuration, but values and element count must match the data in the controller.

## 13. Common Errors

| Error | Cause | Fix |
| --- | --- | --- |
| JSON body cannot be decoded | Missing Jackson or mismatched Content-Type | Check dependencies and Content-Type |
| WebClient throws DataBufferLimitException | Response to aggregate exceeds maxInMemorySize | Reduce payload, stream data, or raise limit in a controlled way |
| Server accepts payload but WebClient fails | Client limit differs from server limit | Configure codecs on the side reading data |
| Custom decoder is not selected | Target type or media type unsupported; misregistered | Check canDecode/canRead and MediaType |
| Custom codec unexpectedly shadows default codec | Reader-writer ordering/priority is not as expected | Inspect reader/writer list and register the proper type |
| JSON codec disappears after configuration | Called registerDefaults(false) | Keep defaults or explicitly register all needed codecs |
| Multipart upload holds too much memory | Non-file parts or file threshold is too large | Configure maxInMemorySize, disk usage, and maxParts |
| Memory leak with Netty | Pooled DataBuffer is not released | Manage ownership and release in custom codecs |
| Released buffer is still read | Released too early or wrong ownership | Release only when consumer no longer needs the buffer |
| Leak occurs only on cancel/error | Cleanup only handles happy path | Handle error, cancellation, and doOnDiscard |
| JSON Flux collected into one array | application/json is non-streaming representation by default | Use NDJSON/SSE or an appropriate streaming type |
| Flux<String> does not produce a JSON string array | String is treated as CharSequence/serialized content | Use Mono<List<String>> if a JSON array is needed |
| Logs expose tokens/cookies | Enabled request detail logging or logged raw bodies | Redact data, disable detail logging |
| Boot loses auto-config after adding @EnableWebFlux | Switched to explicit WebFlux configuration mode | Remove @EnableWebFlux if only WebFluxConfigurer is needed |
| Raised limit very high yet still runs out of memory | Many concurrent large requests or unbounded aggregation | Design for streaming, limit concurrency and payload size |

## 14. Codec Selection and Configuration Checklist

Before changing codecs, check:

1. Is the data to read/write JSON, text, binary, form, multipart, SSE, or NDJSON?
2. Is this server or client configuration? Pick ServerCodecConfigurer or ClientCodecConfigurer for the right side.
3. Are default codecs sufficient? If only changing memory limits, use defaultCodecs.
4. If adding a custom format, does the custom codec declare the exact target type and media type?
5. Does the custom codec support backpressure and process buffers in a non-blocking way?
6. Are there reasonable buffering limits for payloads, multipart parts, and stream elements?
7. Do you truly need to aggregate the entire body, or can you use Flux/streaming?
8. Are DataBuffers properly released on success, error, and cancel?
9. Does the custom codec need registerWithDefaultConfig to receive common settings?
10. Is there a clear reason to call registerDefaults(false)?
11. Could logging expose Authorization headers, cookies, or sensitive bodies?
12. Do tests cover Content-Type, large payloads, NDJSON, multipart, and codec errors?

## 15. API Selection Summary

| Need | API to use |
| --- | --- |
| Customize WebFlux server default codecs | `WebFluxConfigurer.configureHttpMessageCodecs(ServerCodecConfigurer)` |
| Increase server buffer limit | `ServerCodecConfigurer.defaultCodecs().maxInMemorySize(...)` |
| Register custom server readers/writers | `ServerCodecConfigurer.customCodecs()` |
| Customize WebClient codecs | `WebClient.Builder.codecs(Consumer<ClientCodecConfigurer>)` |
| Create a standalone strategy for WebClient | `ExchangeStrategies.builder().codecs(...).build()` |
| Attach strategy to WebClient | `WebClient.Builder.exchangeStrategies(...)` |
| Get default strategy | `ExchangeStrategies.withDefaults()` |
| Create an empty strategy | `ExchangeStrategies.empty()` |
| Clone strategy for modification | `ExchangeStrategies.mutate()` |
| Release pooled buffer | `DataBufferUtils.release(...)` |
| Bounded join of buffer stream | `DataBufferUtils.join(...)` |
| Clean up discarded buffers | `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` |

## 16. Official References

- [Spring Framework – WebFlux Config: HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): configuring ServerCodecConfigurer, default codecs, and custom readers/writers.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): configuring WebClient.Builder, codecs, ExchangeStrategies, and maxInMemorySize.
- [Spring Framework – Reactive Core / Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Encoder, Decoder, HttpMessageReader, HttpMessageWriter, JSON streaming, multipart, and logging.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBufferFactory, PooledDataBuffer, DataBufferUtils, retain/release, and doOnDiscard.
- [CodecConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/CodecConfigurer.html): defaultCodecs, customCodecs, registerDefaults, getReaders/getWriters.
- [ServerCodecConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html): server-side codec configuration.
- [ClientCodecConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ClientCodecConfigurer.html): client-side codec configuration.
- [ExchangeStrategies Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeStrategies.html): builder, withDefaults, empty, and mutate.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): Spring Boot auto-configuration and CodecCustomizer.

## 17. Key Takeaway

**ServerCodecConfigurer manages codecs on the WebFlux server side; ClientCodecConfigurer manages codecs on the client side; ExchangeStrategies encapsulates the readers/writers used by WebClient.** Both sides provide default codecs, customizable via defaultCodecs and extensible via customCodecs.

Keep default codecs when you only need to change a limit or one encoder/decoder. Use ExchangeStrategies when you want to package and reuse a client configuration; for most cases, WebClient.Builder.codecs is more concise. The default buffering limit of around 256 KiB prevents aggregating overly large payloads; raising the limit should be based on data size and concurrency. If you need to process large data, prefer streaming and backpressure. When working directly with DataBuffer, always define ownership and release properly across success, error, and cancellation paths to avoid memory leaks or use-after-release bugs.
