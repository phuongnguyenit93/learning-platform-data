# Encoder, Decoder, HttpMessageReader, and HttpMessageWriter

In **Spring WebFlux**, HTTP requests and responses pass through a conversion chain between bytes and Java objects. Clients send bytes according to a media type such as JSON, form, or binary; controllers typically want to receive a DTO, String, Resource, or Flux. When returning a response, the controller emits an object or publisher and the framework must encode it into bytes to write out to the HTTP connection.

Spring divides this work into two layers:

- **Encoder and Decoder** are low-level codec contracts. An Encoder converts a publisher of objects into a DataBuffer stream; a Decoder converts a DataBuffer stream into objects.
- **HttpMessageReader and HttpMessageWriter** are contracts at the HTTP layer. A Reader reads the body from a ReactiveHttpInputMessage; a Writer writes the body into a ReactiveHttpOutputMessage. They are also aware of media types, data types, and HTTP metadata.

DataBuffer is the byte buffer unit used by codecs. On Netty-based servers, buffers can be pooled and reference-counted; if your code handles DataBuffer directly, it must manage lifecycle release properly. When using default codecs, Spring handles most of this responsibility.

This lesson walks through the request/response flow, the interfaces and default codecs, codec configuration, WebClient, memory limits, DataBuffer ownership, and a runnable Java 17 application with JSON, NDJSON, and raw bytes examples.

## 1. Learning Objectives

After this lesson, you can:

1. Describe the path from an HTTP body to a Java object through HttpMessageReader and Decoder.
2. Describe the path from an object/publisher to an HTTP response through Encoder and HttpMessageWriter.
3. Distinguish low-level Encoder/Decoder from HTTP-layer Reader/Writer.
4. Understand the roles of DataBuffer, DataBufferFactory, DataBufferUtils, and pooled buffers.
5. Choose appropriate media types for JSON, text, binary, form, multipart, NDJSON, and SSE.
6. Configure default codecs, maxInMemorySize, and custom codecs using ServerCodecConfigurer.
7. Configure ClientCodecConfigurer/WebClient to read and write the same formats.
8. Avoid DataBuffer leaks, double releases, holding buffers too long, and buffering large bodies into RAM.
9. Understand DataBufferLimitException, per-object limits during streaming, and multipart-specific limits.
10. Write and test a WebFlux controller using JSON, NDJSON, and DataBuffer directly.

## 2. The Big Picture: From Bytes to Objects and Back

A JSON request arriving at a controller can follow this path:

~~~text
HTTP request
Content-Type: application/json
Body bytes
    |
    v
ReactiveHttpInputMessage
    |
    v
HttpMessageReader
    |
    v
Decoder (e.g., Jackson JSON)
    |
    v
DataBuffer stream -> Java object / Flux<Object>
    |
    v
Controller method
~~~

When returning a response, the processing flow goes in the reverse direction:

~~~text
Controller return value
Mono<Book> / Flux<Book> / Book
    |
    v
HttpMessageWriter
    |
    v
Encoder (e.g., Jackson JSON)
    |
    v
Java object -> DataBuffer stream
    |
    v
ReactiveHttpOutputMessage
    |
    v
HTTP response bytes
~~~

This is the general model. Some specialized readers/writers handle HTTP formats directly without a simple Decoder/Encoder underneath, such as readers for form or multipart. However, the boundary remains the same: Reader/Writer handles the HTTP message; codec transforms data between byte buffers and application types.

WebFlux uses Reactive Streams for non-blocking reading/writing and demand coordination. When the body is a publisher, the framework can process elements one by one instead of waiting for the entire content to be aggregated into a single large byte array.

## 3. Encoder and Decoder

The low-level interfaces live in the org.springframework.core.codec package.

### 3.1. Encoder

Encoder<T> converts a publisher of T into a publisher of DataBuffer:

~~~text
Publisher<T>
    |
    v
Encoder<T>
    |
    v
Publisher<DataBuffer>
~~~

Core responsibilities:

- Check whether a data type and media type are supported, via canEncode.
- Encode a single value if the implementation supports encodeValue.
- Encode a publisher into a DataBuffer stream via encode.
- Provide the MIME types that the encoder supports.

Conceptual example: the Jackson JSON encoder receives a Book or Flux<Book> and produces the corresponding JSON bytes. The String encoder receives strings and encodes them into bytes according to the charset/media type.

An Encoder does not decide the full HTTP status or response headers on its own. Selecting the writer and media type belongs to the HTTP message layer.

### 3.2. Decoder

Decoder<T> works in the opposite direction: it receives a DataBuffer publisher and produces an object publisher:

~~~text
Publisher<DataBuffer>
    |
    v
Decoder<T>
    |
    v
Publisher<T>
~~~

Core responsibilities:

- Check whether the target type and media type can be decoded via canDecode.
- Read the byte stream and construct objects.
- Support decodeToMono when a single aggregated result is needed, if provided by the implementation.
- Manage consumed buffers, discarded buffers, errors, and cancellation.

Example: the Jackson JSON decoder receives JSON bytes and creates a CreateBookRequest. The String decoder converts bytes to String. A decoder for binary data can keep the data as DataBuffer, ByteBuffer, or byte[] depending on the target type.

### 3.3. Encoder/Decoder Are Not HTTP Message Converters

Encoder/Decoder are designed to convert between byte content and objects, independent of the full HTTP message. They are not the sole place handling Content-Type, Accept, status, or headers.

Spring provides adapters to use them at the HTTP layer:

- EncoderHttpMessageWriter wraps an Encoder and provides the HttpMessageWriter contract.
- DecoderHttpMessageReader wraps a Decoder and provides the HttpMessageReader contract.

Specialized readers/writers such as FormHttpMessageReader, MultipartHttpMessageReader, or ServerSentEventHttpMessageWriter can directly implement HTTP logic tailored to their format.

## 4. HttpMessageReader and HttpMessageWriter

### 4.1. HttpMessageReader<T>

HttpMessageReader<T> reads from a ReactiveHttpInputMessage and decodes the body into objects:

~~~text
ReactiveHttpInputMessage
  headers + body DataBuffer
          |
          v
   HttpMessageReader<T>
          |
          v
     Publisher<T>
~~~

Conceptually important methods:

| API | Role |
| --- | --- |
| canRead(elementType, mediaType) | Checks whether the reader can read this type and media type. |
| getReadableMediaTypes() | Returns the media types supported by the reader. |
| read(...) | Reads the body into a multi-element publisher. |
| readMono(...) | Reads the body into a Mono for a single value or an aggregated body. |

A reader is typically chosen based on the controller parameter type and the request's Content-Type. For example, a @RequestBody CreateBookRequest parameter with application/json matches the JSON reader when the Jackson codec is present.

### 4.2. HttpMessageWriter<T>

HttpMessageWriter<T> writes a publisher of objects as bytes into a ReactiveHttpOutputMessage:

~~~text
Publisher<T>
      |
      v
HttpMessageWriter<T>
      |
      v
ReactiveHttpOutputMessage
  headers + body DataBuffer
~~~

Important methods:

| API | Role |
| --- | --- |
| canWrite(elementType, mediaType) | Checks whether the writer can write the type and media type. |
| getWritableMediaTypes() | Returns the media types supported by the writer. |
| write(...) | Writes a publisher of objects into the HTTP output message. |

The appropriate writer is chosen based on the return value type, the media type declared by the controller via produces, and the client's Accept header.

### 4.3. Relationship Among the Four Interfaces

| Interface | Layer | Conversion Direction | Input | Output |
| --- | --- | --- | --- | --- |
| Encoder<T> | Low-level codec | Encode | Publisher<T> | Publisher<DataBuffer> |
| Decoder<T> | Low-level codec | Decode | Publisher<DataBuffer> | Publisher<T> |
| HttpMessageReader<T> | HTTP | Read/decode request | ReactiveHttpInputMessage | Publisher<T> |
| HttpMessageWriter<T> | HTTP | Encode/write response | Publisher<T> | ReactiveHttpOutputMessage |

For codecs based on Encoder/Decoder, adapters serve as the bridge:

~~~text
Decoder<T> -- DecoderHttpMessageReader --> HttpMessageReader<T>

Encoder<T> -- EncoderHttpMessageWriter --> HttpMessageWriter<T>
~~~

Not every Reader/Writer is just an adapter. Readers for form or multipart must handle specific HTTP structures; writers for SSE must produce properly formatted event framing.

## 5. Media Types and Content Negotiation

Codecs are not selected solely based on Java class names. Spring also considers the media type.

Two important headers:

- **Content-Type** describes the format of the body sent by the client.
- **Accept** describes the response format the client wants to receive.

Example:

~~~http
POST /api/books
Content-Type: application/json
Accept: application/json
~~~

A JSON request requires a reader capable of reading the DTO type with application/json. A DTO response requires a writer capable of writing application/json.

If a request uses a Content-Type that no reader supports, you typically receive 415 Unsupported Media Type. If the client requests an Accept incompatible with any writable writer, you typically receive 406 Not Acceptable. Malformed or undecodable JSON can turn into a request body read error, typically handled as a bad request.

### 5.1. Common Formats

| Media type | Typical data types | Typical codec/reader/writer |
| --- | --- | --- |
| application/json | DTO, Map, record, collection | Jackson JSON |
| application/x-ndjson | Independent JSON lines | Jackson streaming/NDJSON |
| text/plain | String | String codec |
| application/octet-stream | byte[], ByteBuffer, DataBuffer, Resource | Byte array/Resource/DataBuffer codec |
| application/x-www-form-urlencoded | MultiValueMap<String,String> | Form reader/writer |
| multipart/form-data | Part, FilePart, PartEvent | Multipart reader/writer |
| text/event-stream | ServerSentEvent<T> or event data | SSE reader/writer |

Specific media type names and support depend on the codec/version. Declare matching consumes/produces and inspect the readable/writable media types list of your running configuration.

### 5.2. JSON Array vs. NDJSON Streaming

A Flux<Book> with application/json is typically encoded as a JSON array:

~~~json
[
  {"id":"b-1","title":"Reactive Basics"},
  {"id":"b-2","title":"WebFlux in Practice"}
]
~~~

With application/x-ndjson, each object is encoded as a separate JSON line:

~~~text
{"id":"b-1","title":"Reactive Basics"}
{"id":"b-2","title":"WebFlux in Practice"}
~~~

NDJSON suits streams of independent items, allowing clients to process each record as it arrives. A regular JSON array requires array opening/closing structure and a different consumption model. Choose the format based on the client contract, not merely because the controller returns a Flux.

### 5.3. SSE vs. NDJSON

Server-Sent Events use text/event-stream and event framing with fields such as data, id, event, and retry. NDJSON is just lines of JSON. If you need event IDs, event names, or retry hints, use ServerSentEvent<T> and the SSE writer.

For long-lived streams, send data or periodic heartbeats so client disconnects are detected sooner. A Flux that emits nothing for a long period may delay disconnect detection depending on the server/client.

## 6. Default Codecs in Spring WebFlux

WebFlux provides default readers/writers based on the classpath and configuration. Common groups include:

- Byte array, ByteBuffer, DataBuffer, Resource, and String.
- Jackson JSON and certain other Jackson formats when the corresponding dependency is present.
- Form URL encoded.
- Multipart.
- Server-Sent Events.
- Certain formats such as XML or Protocol Buffers when appropriate dependencies/codecs are added.

Spring Boot auto-configures default HttpMessageReader and HttpMessageWriter instances based on libraries on the classpath. WebFlux and WebClient use similarly structured codecs, but the server side uses ServerCodecConfigurer and the client side uses ClientCodecConfigurer.

You do not need to create Jackson readers/writers manually for every controller. When the WebFlux starter and appropriate Jackson dependencies are present, @RequestBody DTO and returning DTOs usually work out of the box.

### 6.1. Checking Formats by Classpath

If you add a Jackson dependency, the JSON codec can be auto-configured. If you add a new format library, check:

1. Is the codec registered?
2. Does the codec support the required Java types?
3. Does the codec support the right Content-Type/Accept?
4. Does the codec have appropriate buffering limits?
5. Are there conflicts with another codec that has a broader media type?

Adding a dependency does not guarantee an endpoint uses the new format if there is no corresponding reader/writer.

## 7. Configuring ServerCodecConfigurer

ServerCodecConfigurer manages the list of server-side readers and writers. It can be customized via WebFluxConfigurer:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024);
    }
}
~~~

This snippet sets the buffering limit of default codecs that support this setting to 512 KiB. It does not mean every request body is capped at 512 KiB in total; the limit and how it applies depend on the codec, especially for streaming and multipart.

### 7.1. Registering Custom Codecs

When a custom format is needed, you can register an Encoder or Decoder; Spring automatically wraps them into the corresponding writer/reader:

~~~java
@Configuration
class CustomCodecConfig implements WebFluxConfigurer {

    private final Decoder<CustomRecord> customDecoder;
    private final Encoder<CustomRecord> customEncoder;

    CustomCodecConfig(
            Decoder<CustomRecord> customDecoder,
            Encoder<CustomRecord> customEncoder) {
        this.customDecoder = customDecoder;
        this.customEncoder = customEncoder;
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.customCodecs()
            .registerWithDefaultConfig(customDecoder);

        configurer.customCodecs()
            .registerWithDefaultConfig(customEncoder);
    }
}
~~~

This is an integration snippet: CustomRecord, customDecoder, and customEncoder must be actual implementations provided by the application. registerWithDefaultConfig registers the codec and applies relevant default configurations such as maxInMemorySize/logging where applicable.

If you already have a complete HttpMessageReader or HttpMessageWriter, register that object directly. When two codecs support the same type and media type, registration order and specificity can affect which codec is chosen; verify with actual requests.

### 7.2. When to Replace Default Codecs?

Only call registerDefaults(false) when you deliberately want full control over the entire list of readers/writers. If you disable default codecs and forget to re-register essential JSON, String, byte array, or multipart codecs, controllers may fail to read/write common bodies.

Normally, you should keep default codecs and add custom codecs. When further configuration is needed in Spring Boot, use WebFluxConfigurer or CodecCustomizer appropriate for your Boot version; do not add @EnableWebFlux just to change a small limit, because that annotation switches the application into self-managed WebFlux configuration mode.

## 8. Configuring Codecs on WebClient

WebClient uses the same codec family to encode request bodies and decode response bodies:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("https://api.example.test")
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024)
    )
    .build();

Mono<Book> book = client.get()
    .uri("/books/b-1")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(Book.class);
~~~

This is an integration snippet; Book is an application DTO. This configuration sets a 1 MiB maxInMemorySize for client default codecs that support the limit.

Ways to consume the body:

- bodyToMono(Book.class): decode a single object.
- bodyToFlux(Book.class): decode a stream of objects if the media type/codec supports it.
- toEntity(Book.class): get a ResponseEntity with status/headers/body.
- toBodilessEntity(): get only response metadata when the body is not needed.

For large response bodies, consider bodyToFlux or streaming DataBuffer processing instead of bodyToMono into a single object holding the entire content. Do not call block() on an event-loop thread; if integrating with imperative code, place the blocking boundary on an appropriate scheduler/adapter.

## 9. DataBuffer and DataBufferFactory

DataBuffer is Spring's abstraction for byte buffers. It hides differences between implementations such as Netty ByteBuf, Java NIO ByteBuffer, or default buffers.

DataBuffer provides:

- Byte reading and writing with read position/write position.
- Capacity that can grow depending on the implementation.
- Content access via ByteBuffer, InputStream, or OutputStream when needed.
- PooledDataBuffer/reference counting on implementations that support pooling.

DataBufferFactory allocates new buffers or wraps existing byte[]/ByteBuffer instances. In WebFlux applications, typically obtain the factory from the response or client request rather than creating a factory tied to a specific server:

~~~java
DataBufferFactory factory = exchange.getResponse().bufferFactory();

DataBuffer buffer = factory.allocateBuffer();
buffer.write("hello".getBytes(StandardCharsets.UTF_8));
~~~

If your code writes buffers to the response, the response writer assumes ownership of the emitted buffers and is responsible for consuming/releasing them according to contract. Do not release a buffer a second time after transferring ownership to the writer.

## 10. PooledDataBuffer, Reference Counting, and Memory Leaks

Some servers such as Reactor Netty use pooled direct buffers to reduce allocations and copying during I/O. PooledDataBuffer has a reference count:

- When a buffer is allocated, the reference count typically starts at 1.
- retain() increments the reference count when another ownership reference needs to be held.
- release() decrements the reference count.
- When the count reaches 0, the buffer can be returned to the pool.

If code reads a buffer without releasing it promptly, direct memory can be held long-term and cause a leak. If you release more times than retain/ownership allows, you may encounter IllegalReferenceCountException or errors accessing an already-freed buffer.

**Ownership principle:** the component receiving a DataBuffer is responsible for knowing when it finishes consuming it or transfers ownership to another component. Do not release a buffer after passing it to another writer; do not retain buffers across requests or callbacks with unclear lifecycles.

### 10.1. DataBufferUtils.release and retain

Use Spring's utility rather than casting to PooledDataBuffer:

~~~java
DataBufferUtils.release(buffer);
~~~

~~~java
DataBufferUtils.retain(buffer);
~~~

These utilities apply the operation when the implementation supports pooled buffers. For normal business code, avoid holding DataBuffer long-term; decode into DTOs/small byte arrays or use Resource/streaming abstractions where appropriate.

### 10.2. DataBufferUtils.join

When you need to aggregate multiple DataBuffers into one buffer, use DataBufferUtils.join instead of manually concatenating byte arrays piece by piece:

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(buffers);
~~~

join can use a composite buffer to avoid copying all data if the implementation supports it. The resulting buffer must be released after reading completes. With the maxByteCount overload, the application can cap the total bytes allowed to be aggregated:

~~~java
Mono<DataBuffer> joined =
    DataBufferUtils.join(buffers, 1024 * 1024);
~~~

If the data exceeds the threshold, join emits a DataBufferLimitException error. For large streams, consider processing buffer by buffer instead of joining the entire stream.

### 10.3. Example: Reading a Raw Body and Releasing Properly

In a controller, you can accept Flux<DataBuffer>, join a small body, read the byte count, and then release the resulting buffer:

~~~java
@PostMapping(
    path = "/raw-size",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Integer> rawSize(@RequestBody Flux<DataBuffer> body) {
    return DataBufferUtils.join(body, 1024 * 1024)
        .map(buffer -> {
            try {
                return buffer.readableByteCount();
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .defaultIfEmpty(0);
}
~~~

Here, a body up to 1 MiB is aggregated to count bytes. The finally block ensures the joined buffer is released even if reading throws an error. If you only need to forward the body to the response, use writeWith(body) and let the writer take ownership; do not join or release manually if unnecessary.

## 11. Custom Decoders Must Manage Consumed and Discarded Buffers

A Decoder is usually the final place reading DataBuffers before producing higher-level objects. When writing a custom decoder, you must handle:

1. Buffers that have been read and can be released immediately.
2. Buffers dropped by filters, skips, or operators.
3. Buffers retained to assemble multiple chunks before decoding.
4. Errors, cancellation, or downstream stopping demand before buffers are read.
5. Buffers retained extra times that must be released according to the exact ownership count.

If using Reactor operators that may prefetch/cache or drop elements, the decoder needs to handle discards. Important pattern:

~~~java
return input
    .map(this::decodeOne)
    .doOnDiscard(
        DataBuffer.class,
        DataBufferUtils::release
    );
~~~

This is a conceptual skeleton; decodeOne must manage the buffer it receives according to the decoder's ownership. doOnDiscard only handles elements discarded by Reactor in operators that support the discard hook; it does not replace releasing buffers held by the decoder in its own internal state.

When holding multiple buffers to construct one object, release all retained buffers in all three outcomes: successful decode, error, and cancellation. DataBufferUtils.join, skipUntilByteCount, and takeUntilByteCount are utilities worth considering before building a custom aggregation algorithm.

## 12. Custom Encoders Must Handle Errors During Buffer Allocation

An Encoder creates DataBuffers for downstream writing to HTTP. If serialization fails after allocating a buffer but before emitting it outward, the encoder must release the buffer whose ownership has not been transferred.

Example of managing buffers during an encode step:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean handedOff = false;

try {
    // Serialize value and write bytes into buffer.
    serialize(value, buffer);
    handedOff = true;
    return buffer;
}
finally {
    if (!handedOff) {
        DataBufferUtils.release(buffer);
    }
}
~~~

This is an ownership pattern that should be placed inside an appropriate Encoder implementation. Once the buffer is emitted successfully, the downstream consumer is responsible for releasing it when writing completes. Do not release immediately after returning the buffer if the consumer still needs to read it.

## 13. Memory Limits and DataBufferLimitException

Some decoders/readers must buffer part or all of the body in RAM. For example:

- @RequestBody byte[] needs to create a complete byte array.
- Form URL encoded needs to aggregate data to build a MultiValueMap.
- A single JSON object may need to read the body to construct one DTO.
- Streaming decoders must split bytes into individual records/objects.
- Multipart needs to parse each part and may keep non-file parts in memory.

Default codecs have a buffering limit; current Spring documentation states the default is typically **256 KiB** for codecs that enforce this limit. When the limit is exceeded, the application may receive DataBufferLimitException with a message indicating exceeded max bytes to buffer.

### 13.1. Configuring maxInMemorySize

Server side:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

WebClient side:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer -> configurer.defaultCodecs()
        .maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

Both examples set a 2 MiB limit for default codecs that support this setting. Client configuration does not change the server limit and vice versa.

### 13.2. Streaming: Limits Can Apply Per Object

For decoders that split a stream into multiple objects, maxInMemorySize typically applies to the bytes buffered to produce **one object** in the stream, not the total bytes of the entire stream.

For example, NDJSON can emit millions of small lines; if the decoder processes line by line, the total stream can exceed the limit while each record stays below the threshold. A single oversized JSON line can still exceed the limit.

This is why it is important to distinguish:
- One body aggregated into a single object.
- A long stream of many independent objects.
- A byte stream forwarded without aggregation.

Do not raise the global limit just to make one large upload endpoint work. Consider streaming, business size limits, streaming files to storage, and configuring appropriate codecs.

### 13.3. Multipart Has Its Own Limits

For multipart:
- maxInMemorySize limits the size of non-file parts kept in memory.
- For file parts, this value is the threshold before content is written to disk according to the reader implementation.
- maxDiskUsagePerPart limits disk usage for each individual file part.
- maxParts limits the total number of parts in a request.

If you need control over all three, configure MultipartHttpMessageReader/DefaultPartHttpMessageReader accordingly and register the configured reader via ServerCodecConfigurer. Do not treat maxInMemorySize as the total upload size limit or full disk quota.

### 13.4. Increasing the Limit Does Not Mean Increasing Capacity

If you raise maxInMemorySize very high, many concurrent requests can hold substantial RAM. For example, 100 requests each buffering 20 MiB can create roughly 2 GiB of pressure just for held bodies, excluding object graphs and overhead.

Combine:
- Request size limits at the gateway/server and business layer.
- Streaming for files or large payloads.
- Concurrency and queue limits.
- Measuring heap/direct memory, GC, and concurrent requests.
- Choosing maxInMemorySize based on actual record sizes.

DataBufferLimitException alone does not dictate the right business policy. The application can map the error to a status and error body according to the API contract; do not assume a fixed status without configuring exception handling.

## 14. Configuring Multipart and Streaming

### 14.1. FilePart

For file uploads, FilePart allows transferring file content to a destination without turning the entire file into a byte[]:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    Path destination = Paths.get("/tmp/uploads")
        .resolve(UUID.randomUUID().toString());

    return file.transferTo(destination)
        .thenReturn(destination.getFileName().toString());
}
~~~

This is an integration snippet. Use server-generated filenames; if using client filenames for display or metadata storage, validate them and never concatenate them directly into filesystem paths. Enforce size limits, access permissions, content type checks, disk quotas, and temporary file cleanup.

### 14.2. PartEvent When Streaming Multipart

For large uploads or many parts, WebFlux provides the PartEvent API to process multipart as a stream. This allows receiving each part/event and processing data buffer by buffer instead of building a MultiValueMap containing the entire multipart request. When using PartEvent, follow DataBuffer ownership/release rules and consume each part according to the API contract.

### 14.3. NDJSON and SSE

NDJSON fits multiple JSON objects separated by newlines. SSE fits event streams with dedicated framing and optional id/retry/event names. For both, send periodic data/heartbeats so client disconnects are detected earlier, and consider timeouts, subscriber counts, and cancellation.

## 15. Runnable Java 17 Example: JSON, NDJSON, and DataBuffer

The example uses Spring Boot 3.3.5, Java 17, and WebFlux. Boot manages the compatible Spring Framework/Reactor versions. The application demonstrates:
- JSON requests/responses handled by default readers/writers.
- Flux<Book> written as NDJSON.
- An endpoint receiving Flux<DataBuffer>, performing a bounded join, and releasing the buffer.
- ServerCodecConfigurer configuring the buffering limit.

### 15.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 15.2. src/main/java/demo/CodecDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}
~~~

### 15.3. src/main/java/demo/CodecConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024);
    }
}
~~~

### 15.4. src/main/java/demo/BookController.java

~~~java
package demo;

import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record CreateBookRequest(String title, String author) {}
record Book(String id, String title, String author) {}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final ConcurrentMap<String, Book> books =
        new ConcurrentHashMap<>();

    private final AtomicInteger sequence = new AtomicInteger(2);

    BookController() {
        books.put("b-1",
            new Book("b-1", "Reactive Basics", "An"));
        books.put("b-2",
            new Book("b-2", "WebFlux in Practice", "Binh"));
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    Flux<Book> list() {
        return Flux.fromIterable(books.values());
    }

    @GetMapping(
        path = "/stream",
        produces = "application/x-ndjson"
    )
    Flux<Book> stream() {
        return Flux.fromIterable(books.values());
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<Book>> get(@PathVariable String id) {
        return Mono.justOrEmpty(books.get(id))
            .map(book -> ResponseEntity.ok(book))
            .defaultIfEmpty(ResponseEntity.<Book>notFound().build());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<Book>> create(
            @RequestBody Mono<CreateBookRequest> body) {
        return body.map(request -> {
            String id = "b-" + sequence.incrementAndGet();
            Book book = new Book(
                id, request.title(), request.author()
            );
            books.put(id, book);

            return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(book);
        });
    }

    @PostMapping(
        path = "/raw-size",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Integer> rawSize(@RequestBody Flux<DataBuffer> body) {
        return DataBufferUtils.join(body, 1024 * 1024)
            .map(buffer -> {
                try {
                    return buffer.readableByteCount();
                }
                finally {
                    DataBufferUtils.release(buffer);
                }
            })
            .defaultIfEmpty(0);
    }
}
~~~

The raw-size endpoint only aggregates up to 1 MiB for demonstration. Real-world applications should avoid joining large files and instead process them as streams or write them to storage.

### 15.5. src/test/java/demo/BookControllerTest.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class BookControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void jsonReaderAndWriterHandleBookList() {
        client.get()
            .uri("/api/books")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(byte[].class)
            .value(bytes -> {
                String body = new String(bytes, StandardCharsets.UTF_8);
                assertTrue(body.contains("Reactive Basics"));
                assertTrue(body.contains("WebFlux in Practice"));
            });
    }

    @Test
    void ndjsonWriterStreamsIndividualBooks() {
        client.get()
            .uri("/api/books/stream")
            .accept(MediaType.valueOf("application/x-ndjson"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.valueOf("application/x-ndjson")
                )
            .expectBody(byte[].class)
            .value(bytes -> {
                String body = new String(bytes, StandardCharsets.UTF_8);
                assertTrue(body.contains("\"id\":\"b-1\""));
                assertTrue(body.contains("\"id\":\"b-2\""));
            });
    }

    @Test
    void jsonReaderDecodesCreateRequest() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateBookRequest(
                "Codec Handbook", "Chi"
            ))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.title").isEqualTo("Codec Handbook");
    }

    @Test
    void dataBufferBodyIsJoinedAndReleased() {
        byte[] bytes = "abcdef".getBytes(StandardCharsets.UTF_8);

        client.post()
            .uri("/api/books/raw-size")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(bytes)
            .exchange()
            .expectStatus().isOk()
            .expectBody(Integer.class)
            .isEqualTo(6);
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The four tests verify:
- The JSON reader decodes the request DTO and the JSON writer writes the list response.
- The NDJSON writer writes each book as a JSON line.
- POST returns status 201 and Location.
- The raw-size endpoint reads the DataBuffer body, joins within the limit, and releases the buffer after counting.

The initial data contains two fixed books so the two list-reading tests can assert specific names. The POST test adds a book to the map inside the test context; if expanding tests to run in parallel or depend on ordering, create separate fixtures/reset stores per test.

### 15.6. Calling the API with curl

List JSON:

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/books
~~~

Receive NDJSON:

~~~bash
curl -i -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/books/stream
~~~

Create a book:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Codec Handbook","author":"Chi"}'
~~~

Send raw bytes:

~~~bash
curl -i -X POST http://localhost:8080/api/books/raw-size \
  -H "Content-Type: application/octet-stream" \
  --data-binary "abcdef"
~~~

The final response is the JSON number 6. New book IDs increment sequentially starting from b-3. Data creation commands mutate the map in the current process.

## 16. WebClient Stream Reading and DataBuffer Handling

When the client receives a large body, you can use bodyToFlux to process objects item by item:

~~~java
Flux<Book> books = webClient.get()
    .uri("/api/books/stream")
    .accept(MediaType.valueOf("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Book.class);
~~~

If you need to manipulate bytes directly, you can receive DataBuffer:

~~~java
Flux<DataBuffer> buffers = webClient.get()
    .uri("/exports/archive")
    .retrieve()
    .bodyToFlux(DataBuffer.class);
~~~

When working with DataBuffer from WebClient, you must consume or transfer ownership explicitly. If writing to a file/channel, prefer DataBufferUtils.write or an appropriate Resource/streaming API and adhere to that API's contract. If reading and discarding buffers yourself, release them properly. Do not collect all buffers into a List<DataBuffer> to hold indefinitely in heap/direct memory.

## 17. Codec Logging and Observability

When debugging decode/encode errors, check:

1. Request Content-Type and response Accept.
2. Actual Java types of the parameters/return value.
3. Whether the reader/writer supports that media type.
4. Jackson/codec dependencies and ObjectMapper configuration.
5. maxInMemorySize and record/body sizes.
6. Root exception: decode error, DataBufferLimitException, codec-not-found, or serialization error.
7. Direct memory and leak detector if using pooled Netty buffers.

Do not unconditionally enable request/response body logging in production: payloads may contain passwords, tokens, or personal data; logging can also increase allocations and I/O overhead. Only log necessary metadata and mask sensitive data.

When running Reactor Netty, you can enable Netty leak detection in dev/test environments to detect unreleased buffers. Detailed inspection levels carry performance overhead; do not enable the heaviest mode by default on production traffic.

## 18. Common Pitfalls and How to Fix Them

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Thinking Encoder and HttpMessageWriter are the same interface | Failing to distinguish encoding bytes from writing an HTTP message | Understand writer is the HTTP layer; encoder is the low-level codec |
| Thinking every reader/writer wraps a Decoder/Encoder | Overlooking specialized readers/writers for form, multipart, SSE | Use the interface appropriate for the format |
| Content-Type does not match consumes/reader | Request may be rejected with 415 | Send the correct media type and register a supporting reader |
| Accept does not match produces/writer | Response may be rejected with 406 | Adjust Accept/produces or add a writer |
| Using application/json for an infinite stream | Clients must handle a long structured JSON array; mid-stream errors are hard to recover from | Consider NDJSON or SSE according to the contract |
| Joining a large file into a single DataBuffer | Increases memory usage and may exceed maxInMemorySize | Process buffer by buffer or stream to a file |
| Setting a huge maxInMemorySize for all codecs | Many concurrent requests can hold large amounts of RAM/direct memory | Limit per endpoint and use streaming |
| Forgetting to release pooled DataBuffers | Direct memory leak | Use DataBufferUtils.release and define ownership |
| Releasing a buffer after handing it to the response writer | The writer may read an already-freed buffer | Transfer ownership; let the writer release |
| Releasing twice | IllegalReferenceCountException | Track retain/release and ownership |
| Decoder ignoring discarded buffers | Buffer leak on filter/skip/cancel | Use doOnDiscard and clean up internal state |
| Encoder not releasing buffer on serialization error | Unemitted buffer leaks | Use try/finally before handoff |
| Thinking maxInMemorySize is the total stream limit | Misunderstanding limits for NDJSON/streams | Check the decoder's per-object limit |
| Thinking maxInMemorySize controls all multipart quotas | May lack disk and part-count limits | Configure maxDiskUsagePerPart and maxParts |
| Calling registerDefaults(false) and forgetting the JSON codec | Controllers can no longer read/write common formats | Only disable when manually configuring the complete codec list |
| Adding a custom codec without checking canRead/canWrite | Codec is not selected or conflicts with another codec | Verify types, media types, and registration order |
| Creating a Netty-tied DataBufferFactory in shared code | Code becomes coupled to server implementation | Obtain the factory from request/response or client request |
| Buffering body to byte[] when unnecessary | Loses streaming benefits, increases heap | Use Flux/DataBuffer/Resource as appropriate |

## 19. Codec and Buffer Design Checklist

Before implementing an endpoint or custom codec, check:

1. **Data type:** is the body a DTO, String, Resource, byte[], or stream?
2. **Media type:** are request Content-Type and response Accept/produces compatible?
3. **Abstraction layer:** do you need a custom Encoder/Decoder or a custom HttpMessageReader/Writer?
4. **Streaming:** do you need to read/write record by record or can a bounded body be aggregated?
5. **Memory bound:** does maxInMemorySize fit the size of a single object/part?
6. **Multipart:** have non-file memory, disk per part, and maxParts limits been set?
7. **Buffer ownership:** who releases the buffer on success, error, and cancellation?
8. **Discard:** does a custom decoder have doOnDiscard or cleanup for dropped buffers?
9. **Client/server parity:** does WebClient have codec/media type configuration compatible with the server?
10. **Tests:** have WebTestClient/WebClient tests covered JSON, streams, wrong media types, large bodies, and cancellation?
11. **Observability:** do you log metadata and monitor direct memory/leaks without exposing sensitive payloads?
12. **Versions:** are custom codec APIs and Jackson/Protobuf/XML dependencies compatible with your Spring Framework/Boot version?

**Key takeaway:** Encoder/Decoder convert between objects and DataBuffer; HttpMessageReader/HttpMessageWriter apply that to HTTP messages and media types. Default codecs handle most JSON, text, binary, form, multipart, and SSE cases. When working with DataBuffer directly, establish ownership and release across all success, error, and cancellation paths. Set buffering limits based on the size of data being processed, and use streaming when bodies are large or unbounded.

## References

- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework — Reactive Core and HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux Configuration, HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — WebClient Configuration and Codec Limits: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — HttpMessageReader API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/HttpMessageReader.html
- Spring Framework — HttpMessageWriter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/HttpMessageWriter.html
- Spring Framework — CodecConfigurer API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/CodecConfigurer.html
- Spring Boot — Reactive Web Applications and Codecs: https://docs.spring.io/spring-boot/reference/web/reactive.html
