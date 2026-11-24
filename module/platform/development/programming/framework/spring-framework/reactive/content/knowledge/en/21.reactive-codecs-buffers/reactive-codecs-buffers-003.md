# JSON, Strings, Binary Data, and Matching Media Types in Spring WebFlux

## 1. What Problem Do Codecs Solve?

HTTP transmits data over the network as bytes. Java applications typically work with objects, Strings, byte arrays, Resources, or Publishers. Spring WebFlux needs a translation layer between those two worlds: **codecs**.

Examples:

- A client sends JSON bytes with Content-Type set to application/json; WebFlux reads the bytes and uses the JSON decoder to construct a Java object.
- A controller returns a Java record; the JSON encoder converts the object into JSON bytes to send to the client.
- An endpoint returns a String; the String encoder writes text content with the appropriate media type.
- An endpoint returns a byte[] or Resource; the binary/resource writer writes the binary content.
- An endpoint returns a Flux<Item>; the writer can emit elements one by one according to the appropriate streaming format.

Codecs are central to request/response bodies in Spring WebFlux. They govern:

- Which data can be read or written.
- Which Java types correspond to which media types.
- Whether a body is buffered into a single object or streamed incrementally.
- Memory limits when aggregating data.
- How JSON, text, binary, form, multipart, NDJSON, and Server-Sent Events are handled.
- How the server and WebClient are configured so both sides adhere to the same contract.

## 2. Data Reading and Writing Pipeline

WebFlux structures its abstractions across layers:

~~~text
HTTP request bytes
      |
      v
DataBuffer
      |
      v
HttpMessageReader
      |
      v
Decoder
      |
      v
Java object / Mono / Flux
      |
      v
Controller or HandlerFunction
      |
      v
Java object / Publisher
      |
      v
Encoder
      |
      v
HttpMessageWriter
      |
      v
DataBuffer
      |
      v
HTTP response bytes
~~~

When reading a request, WebFlux selects an `HttpMessageReader` capable of reading the Java type and the request's Content-Type. The Reader typically uses a `Decoder` to convert byte content into an object or publisher.

When writing a response, WebFlux selects an `HttpMessageWriter` compatible with the Java type and the media type requested by the endpoint/client. The Writer typically uses an `Encoder` to convert the object into byte content.

| Component | Responsibility | Example |
| --- | --- | --- |
| `Encoder<T>` | Converts objects into byte content | Jackson JSON encoder, String encoder |
| `Decoder<T>` | Converts byte content into objects | Jackson JSON decoder |
| `HttpMessageReader<T>` | Reads an HTTP body and produces objects/publishers | Reading a JSON request body |
| `HttpMessageWriter<T>` | Writes objects/publishers into an HTTP body | Writing a JSON response |
| `DataBuffer` | Abstraction for a byte buffer region | ByteBuffer, Netty ByteBuf |
| `CodecConfigurer` | Registers and configures readers/writers | ServerCodecConfigurer, ClientCodecConfigurer |

`Encoder` and `Decoder` are HTTP-independent data conversion abstractions. `HttpMessageReader` and `HttpMessageWriter` add HTTP context such as headers, Content-Type, body, and Reactive Streams reading/writing semantics.

You do not need to invoke encoders/decoders manually in normal controllers. WebFlux selects codecs based on Java type and media type and performs the conversion.

## 3. Content-Type and Accept: Two Headers Never to Confuse

These two headers determine codec selection in two opposite directions.

- **Content-Type** describes the format of the request body sent by the client.
- **Accept** describes the response format the client wants to receive.

Example of a client sending JSON and requesting a JSON response:

~~~http
POST /api/items
Content-Type: application/json
Accept: application/json

{"id":1,"name":"Keyboard"}
~~~

The server reads the request with the JSON reader because Content-Type is application/json. When writing the response, the server chooses the JSON writer because Accept is application/json and the endpoint supports that format.

| Case | Header | Meaning |
| --- | --- | --- |
| JSON Request | `Content-Type: application/json` | The request body is JSON |
| JSON Response | `Accept: application/json` | The client accepts JSON |
| Text Request | `Content-Type: text/plain` | The request body is plain text |
| Text Response | `Accept: text/plain` | The client wants plain text |
| Binary Request | `Content-Type: application/octet-stream` | The request body is raw byte content |
| Binary Response | `Accept: application/octet-stream` | The client wants raw byte content |

In Spring annotation-based controllers, you can restrict media types using `consumes` and `produces`:

~~~java
@PostMapping(
    value = "/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Item> create(@RequestBody Mono<Item> body) {
    return body;
}
~~~

- Requests with an unsupported Content-Type can be rejected with **415 Unsupported Media Type**.
- Clients requesting an Accept incompatible with what the endpoint supports can receive **406 Not Acceptable**.
- Malformed or undecodable JSON can result in a request body error such as 400 Bad Request depending on exception handling.

If consumes/produces are omitted, WebFlux still uses default codecs and content negotiation. Declaring media types explicitly makes the API contract clearer and easier to test.

## 4. Common Media Type Map

A media type is a label describing a data format. Do not choose one solely from a file extension; choose based on the actual representation of the body.

| Data | Common media type | Common Java types |
| --- | --- | --- |
| JSON object/array | `application/json` | DTO, record, Map, List |
| Plain text | `text/plain` | String |
| HTML | `text/html` | String or Resource |
| XML | `application/xml` or `text/xml` | Object with XML codec, String |
| Generic bytes | `application/octet-stream` | byte[], ByteBuffer, DataBuffer, Resource |
| PNG | `image/png` | byte[], Resource, DataBuffer |
| JPEG | `image/jpeg` | byte[], Resource, DataBuffer |
| PDF | `application/pdf` | Resource or byte[] |
| Form URL encoded | `application/x-www-form-urlencoded` | MultiValueMap<String,String> |
| Multipart | `multipart/form-data` | Part, FilePart, MultiValueMap |
| NDJSON | `application/x-ndjson` | Flux<T> |
| JSON Lines | `application/jsonl` | Flux<T> when the codec supports the media type |
| Server-Sent Events | `text/event-stream` | Flux<ServerSentEvent<T>> |

Default codecs can vary depending on dependencies on the classpath. For instance, Jackson supports JSON; additional codecs may support Smile, JAXB/XML, or Protocol Buffers when the corresponding libraries are added.

Not every Java type automatically supports every media type. Codec selection also depends on registered codecs, configuration, generic types, and their encode/decode capabilities.

## 5. JSON: Java Objects and application/json

JSON is a common format for API data exchange. In WebFlux, Jackson is typically the default codec when Jackson is on the classpath, such as with the Spring Boot WebFlux starter.

DTO example:

~~~java
public record Item(long id, String name) {
}
~~~

Controller receiving and returning JSON:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {
    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Item> echo(@RequestBody Mono<Item> item) {
        return item;
    }
}
~~~

Client sends:

~~~http
POST /api/items
Content-Type: application/json
Accept: application/json

{"id":7,"name":"Monitor"}
~~~

WebFlux decodes the body into `Item`, the controller receives `Mono<Item>` and returns the publisher. The JSON writer serializes Item into the response body.

For a single body, you can use `Mono<Item>` or `Item` depending on the data source. If services are reactive, keep the publisher and compose with `map`/`flatMap`; never call `block()` just to unwrap and return the object.

### 5.1. JSON Objects, Lists, and Flux

- `Mono<Item>` typically represents one JSON object.
- `Mono<List<Item>>` represents an already-created/aggregated list.
- `Flux<Item>` represents multiple items that may be emitted over time.

With `application/json`, multiple elements are typically written as a JSON array according to the JSON writer's semantics. When each object must be an independent record consumable line by line, use NDJSON/JSON Lines.

Avoid collecting a very large Flux with collectList just to return JSON if the client can process streaming. Buffering all data increases memory usage and latency before the first byte is sent.

### 5.2. Jackson and Data Types

Spring Boot auto-configures the Jackson codec when the library is on the classpath. Types such as records, enums, collections, and Java time types can be serialized/deserialized depending on ObjectMapper configuration and registered modules.

If custom JSON formatting is needed, configure the ObjectMapper/Jackson builder or custom serializers/deserializers. Avoid creating a new ObjectMapper per request; configure a shared bean.

Example record with a timestamp:

~~~java
public record AuditEvent(
    long id,
    String action,
    Instant createdAt
) {
}
~~~

With the Jackson Java Time module configured, the Instant field can be represented in ISO-8601 format. The contract should clearly specify timezone and format when multiple systems consume it.

## 6. String and text/plain

String is text data, not JSON by default. If an endpoint returns a message string or text content, use `text/plain`:

~~~java
@GetMapping(
    value = "/message",
    produces = MediaType.TEXT_PLAIN_VALUE
)
Mono<String> message() {
    return Mono.just("Hello WebFlux");
}
~~~

The response looks like:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

Hello WebFlux
~~~

Points to remember:

- `text/plain` fits plain text.
- `text/html` fits HTML.
- `application/json` fits a JSON representation.
- The charset should be specified consistently, typically UTF-8.
- If a String contains JSON content, do not assume Spring will treat it as JSON just because the string has curly braces. Declare the JSON media type explicitly and ensure the string is valid JSON.

Example returning a JSON string:

~~~java
@GetMapping(
    value = "/raw-json",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<String> rawJson() {
    return Mono.just("{\"status\":\"ok\"}");
}
~~~

In this example, the application is responsible for producing valid JSON. For normal Java objects, let Jackson serialize them instead of concatenating JSON strings manually, which is error-prone for escaping, encoding, and structure.

## 7. Binary Data: byte[], ByteBuffer, DataBuffer, and Resource

A binary body is byte content not meant to be interpreted as text. The media type must accurately describe the content, such as application/octet-stream, image/png, or application/pdf.

### 7.1. byte[]

~~~java
@GetMapping(
    value = "/binary",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
Mono<byte[]> binary() {
    byte[] bytes = "BINARY".getBytes(StandardCharsets.UTF_8);
    return Mono.just(bytes);
}
~~~

`byte[]` is simple and convenient when the payload is small or already in memory. However, the entire byte array must reside on the heap; it is unsuitable for serving very large files if data can be streamed from a source.

### 7.2. ByteBuffer

`ByteBuffer` is Java NIO's abstraction for byte data. Codecs can encode/decode ByteBuffer without converting through String. Pay attention to position, limit, and buffer reuse because this state affects what data is read.

### 7.3. Resource

`Resource` fits when the response is a file or a streamable resource:

~~~java
@GetMapping(value = "/manual.pdf", produces = MediaType.APPLICATION_PDF_VALUE)
Mono<Resource> manual() {
    Resource file = new FileSystemResource("/srv/app/manual.pdf");
    return Mono.just(file);
}
~~~

The `Resource` writer can read content from the resource in a manner suitable for an HTTP response. For large files, this is usually better than reading the whole file into a byte[] before returning the response.

File paths should come from trusted configuration or a storage service; never concatenate client-supplied paths directly onto the filesystem. Check access permissions, file existence, and media type.

### 7.4. DataBuffer

`DataBuffer` is a lower-level abstraction, closer to the transport byte buffer. Use it when you need to process a byte stream directly, such as proxying data, custom encoding/decoding, or specialized streaming operations.

If you only need to return a normal file or byte[], prefer Resource/byte[] so codecs manage the buffers. When creating or consuming DataBuffer yourself, understand buffer ownership and lifecycle.

## 8. NDJSON and Streaming JSON

NDJSON (newline-delimited JSON) represents each JSON object on its own line. It suits streams consisting of many independent records.

Body example:

~~~text
{"id":1,"name":"Mai"}
{"id":2,"name":"An"}
{"id":3,"name":"Binh"}
~~~

Endpoint:

~~~java
@GetMapping(
    value = "/items/stream",
    produces = "application/x-ndjson"
)
Flux<Item> streamItems() {
    return Flux.just(
        new Item(1, "Mai"),
        new Item(2, "An"),
        new Item(3, "Binh")
    );
}
~~~

Differences:

| JSON array | NDJSON |
| --- | --- |
| One JSON document containing an array | Each line is a separate JSON document |
| Clients usually parse the whole document/array | Clients can parse line by line |
| Fits moderately sized finite list responses | Fits streaming records over time |
| Media type application/json | Typically uses application/x-ndjson |

Streaming formats reduce the need to aggregate all data. However, client and server must agree on framing. Never emit adjacent JSON objects without delimiters and expect the client to guess record boundaries.

## 9. Server-Sent Events: text/event-stream

SSE is a protocol where the server pushes unidirectional events to the client over HTTP. WebFlux has a codec supporting `ServerSentEvent<T>`.

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<String>> events() {
    return Flux.just("connected", "updated")
        .map(value -> ServerSentEvent.builder(value)
            .event("status")
            .build());
}
~~~

SSE is commonly used for dashboards, notifications, or progress updates. An event can include:

- `id`: event identifier.
- `event`: event type.
- `retry`: suggested retry interval.
- `data`: payload content.
- Comment/heartbeat: keeps the connection alive and helps detect disconnected clients.

SSE is a text protocol with media type text/event-stream; do not use application/json merely because the data inside the event is JSON. If an event holds an object, the codec serializes the data field according to SSE configuration.

For long-lived streams, consider periodic heartbeats. If no bytes are sent for a long time, proxies or servers may not detect client disconnects promptly. Spring recommends sending periodic data on streaming responses to detect disconnects.

## 10. Form URL Encoded and Multipart

Not every HTTP body is JSON.

### 10.1. application/x-www-form-urlencoded

This is a simple form format where data is encoded as key/value pairs:

~~~http
POST /login
Content-Type: application/x-www-form-urlencoded

username=mai&remember=true
~~~

In a functional endpoint, you can read it as:

~~~java
Mono<ServerResponse> login(ServerRequest request) {
    return request.formData()
        .flatMap(form -> {
            String username = form.getFirst("username");
            String remember = form.getFirst("remember");
            return ServerResponse.ok()
                .bodyValue("user=" + username + ", remember=" + remember);
        });
}
~~~

`formData()` returns a Mono of MultiValueMap. Parsing can aggregate form content, so it is still subject to appropriate memory limits.

### 10.2. multipart/form-data

Multipart fits file uploads accompanied by metadata:

~~~http
POST /upload
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="description"

Profile photo
--boundary
Content-Disposition: form-data; name="file"; filename="photo.png"
Content-Type: image/png

...binary bytes...
--boundary--
~~~

In a WebFlux controller, you can accept `FilePart`:

~~~java
@PostMapping(
    value = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<ResponseEntity<Void>> upload(
        @RequestPart("file") FilePart file) {

    return uploadService.store(file)
        .thenReturn(ResponseEntity.accepted().build());
}
~~~

`FilePart` provides the filename, headers, and content reactively. The service should write files to a configured directory/storage, generate filenames server-side, and validate size, file type, and permissions. Never trust client-provided filenames.

With a functional endpoint:

~~~java
Mono<ServerResponse> upload(ServerRequest request) {
    return request.multipartData()
        .flatMap(parts -> {
            Part file = parts.getFirst("file");
            return uploadService.store(file)
                .then(ServerResponse.accepted().build());
        });
}
~~~

Multipart has dedicated limits such as part count, header size, per-part memory limit, and disk usage limit. Configure limits appropriate to the upload use case.

## 11. Buffering, maxInMemorySize, and DataBufferLimitException

Some codecs must aggregate data before decoding/encoding. For example:

- Reading a request into a byte[] or a large single JSON object.
- Reading URL-encoded form data.
- Reading a multipart part.
- Splitting a stream into JSON/delimited text records.

To prevent large payloads from consuming unbounded memory, codecs enforce buffer limits. Default codecs typically have a 256 KB limit for cases requiring aggregation, though the actual limit depends on the codec and configuration. When exceeded, the application may receive `DataBufferLimitException` indicating exceeded max bytes to buffer.

**Raising the limit is not a cure-all for every error.** First examine whether the body actually needs aggregation or can be streamed. If large payloads are legitimate, choose per-element reading/writing or Resource/FilePart rather than loading the entire body into one object.

### 11.1. Configuring in Spring Boot

In `application.properties`:

~~~properties
spring.codec.max-in-memory-size=1MB
~~~

This property applies to WebFlux server and WebClient instances auto-configured by Spring Boot. It sets the limit for data requiring aggregation; individual codecs may still have specific behaviors/limits.

### 11.2. Configuring the Server with WebFluxConfigurer

~~~java
@Configuration
public class WebCodecConfiguration implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024);
    }
}
~~~

This configures a 1 MiB limit for server-side default codecs. In Spring Boot, you can add a WebFluxConfigurer while preserving auto-configuration. Only use @EnableWebFlux if you want full manual control over WebFlux configuration.

### 11.3. Multipart Limits

Spring Boot provides dedicated properties for multipart, for example:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-parts=20
spring.webflux.multipart.max-disk-usage-per-part=100MB
~~~

- max-in-memory-size controls the threshold for parts kept in memory before spilling to disk.
- max-parts limits the number of parts in a request.
- max-disk-usage-per-part limits disk space per part.

Exact settings should match your application's upload sizes and storage capacity. Avoid setting -1 or disabling limits in public environments without other resource controls.

## 12. DataBuffer Lifecycle and Avoiding Memory Leaks

`DataBuffer` can be backed by regular buffers or pooled buffers. On servers such as Reactor Netty, byte buffers can be pooled and reference-counted. When the application consumes buffers directly, it must release them promptly to avoid memory leaks.

Principles:

1. If you only use codecs at the object/String/Resource level, let Spring manage DataBuffers.
2. If you consume or discard a DataBuffer yourself, verify ownership and release properly.
3. If passing a buffer downstream for further writing, do not release it before downstream completes.
4. Never release the same buffer twice.
5. Never retain references to a pooled buffer after releasing it.
6. With custom codecs, adhere to the contracts of Encoder/Decoder and DataBufferFactory.

Example releasing when the application owns the buffer:

~~~java
DataBuffer buffer = ...;
try {
    // Read/copy required bytes from the buffer.
} finally {
    DataBufferUtils.release(buffer);
}
~~~

This is an illustrative snippet; only release when your code truly owns the buffer and does not pass it onward to another component. When working with buffer streams, handle error/cancel paths and every allocated buffer.

`DataBufferUtils.join` can merge multiple buffers into one buffer, but aggregation still needs size bounds. Never use join to turn a large file into one giant buffer when streaming is the goal.

## 13. Configuring and Registering Custom Codecs

WebFlux includes many default readers/writers. When a custom media type or format is needed, you can add custom codecs.

### 13.1. ServerCodecConfigurer

~~~java
@Configuration
public class CustomCodecConfiguration implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(1024 * 1024);

        configurer.customCodecs()
            .register(new MyMessageEncoder());

        configurer.customCodecs()
            .register(new MyMessageDecoder());
    }
}
~~~

`MyMessageEncoder` must implement Encoder<MyMessage>; `MyMessageDecoder` must implement Decoder<MyMessage>. Each codec must declare supported media types, type encoding/decoding capability, and buffer/backpressure handling.

### 13.2. Encoder and Decoder

A custom Encoder typically must specify:

- Supported Java types.
- Writable media types.
- Ability to encode a single value or a Publisher.
- How DataBuffers are created from byte content.
- How hints and streaming are handled, if applicable.

A custom Decoder typically must specify:

- Output Java type.
- Readable media types.
- How the byte stream is parsed into objects.
- How record boundaries across buffers are handled.
- How malformed input, cancellation, and buffer releases are handled.

Do not write a custom codec if default Jackson/String/byte[]/Resource codecs already meet your needs. Hand-written codecs are low-level and can cause memory, framing, or compatibility bugs if contracts are violated.

### 13.3. WebClient Codecs

WebClient has its own codec set for client requests/responses:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024))
    .build();
~~~

Sending a JSON object:

~~~java
Mono<Item> created = client.post()
    .uri("/api/items")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(new Item(7, "Monitor"))
    .retrieve()
    .bodyToMono(Item.class);
~~~

Reading NDJSON into a Flux:

~~~java
Flux<Item> items = client.get()
    .uri("/api/items/stream")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Item.class);
~~~

`bodyToMono` typically aggregates a response body into one value; `bodyToFlux` fits when the response streams multiple elements. For error responses, use `onStatus` or handle WebClientResponseException to map HTTP errors per contract.

## 14. Choosing Codecs and Media Types: Diagnostic Steps

When encountering a codec error, check in order:

1. Does request Content-Type match the actual body format?
2. Does the endpoint have matching consumes?
3. Is client Accept compatible with the endpoint's produces?
4. Is the Java type supported by a codec?
5. Is the required codec dependency on the classpath and registered?
6. Is the body malformed or using the wrong charset?
7. Does the body exceed maxInMemorySize?
8. For multipart, are max parts, memory, disk, or header limits exceeded?
9. If using DataBuffer directly, are buffers retained/released following lifecycle rules?
10. For streams, does the client understand NDJSON/SSE framing and consume fast enough?

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| 415 Unsupported Media Type | Content-Type unsupported by endpoint/reader | Send the right Content-Type or add a codec |
| 406 Not Acceptable | Accept incompatible with response representation | Fix Accept or declare a matching representation |
| 400 when reading JSON | Malformed JSON, invalid field/type | Check payload and decoder/validation |
| DataBufferLimitException | Body needing aggregation exceeds limit | Stream data or raise limit in a controlled way |
| String body misinterpreted | Wrong media type or charset chosen | Declare text/plain or application/json per contract |
| Corrupted binary data | Improper text encoding or wrong buffer position | Use byte[]/Resource/DataBuffer properly |
| Upload spikes RAM | Reading entire file into byte[] | Use FilePart/Resource streaming and multipart limits |
| Stream only appears at the end | Client/proxy buffering or non-streaming format | Choose NDJSON/SSE, proper flush/heartbeat |
| Memory leak with Netty | Pooled DataBuffer not released | Check ownership and DataBufferUtils.release |
| Codec not found | Codec does not support Java type/media type or is unregistered | Configure custom codec or use a supported type/media type |

## 15. Complete Java 17+ Spring Boot WebFlux Demo

This demo illustrates four representations: JSON, text, binary, and NDJSON. It also verifies Content-Type/Accept behavior with 415 and 406 statuses.

### 15.1. Project Structure

~~~text
webflux-codec-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      Item.java
      CodecController.java
      WebCodecConfiguration.java
    main/resources/
      application.properties
    test/java/demo/
      CodecControllerTest.java
~~~

### 15.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management selects compatible versions of Spring Framework, Reactor, Jackson, and test libraries. Do not pin codec versions separately without a compatibility reason.

### 15.3. application.properties

~~~properties
spring.application.name=webflux-codec-demo
spring.codec.max-in-memory-size=1MB
~~~

The demo sets the default codecs' aggregation limit to 1 MiB to illustrate configuration. In production, choose thresholds based on valid payload sizes and application resources.

### 15.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 15.5. Item.java

~~~java
package demo;

public record Item(long id, String name) {
}
~~~

### 15.6. WebCodecConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebCodecConfiguration implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024);
    }
}
~~~

This configuration shows how to change the server-side limit. You can use either application.properties or WebFluxConfigurer; there is no need to set both to the same value unless you have a specific purpose.

### 15.7. CodecController.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class CodecController {

    @GetMapping(
        value = "/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Item> item(@PathVariable long id) {
        return Mono.justOrEmpty(
            id == 1L ? new Item(1L, "Keyboard") : null
        );
    }

    @PostMapping(
        value = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Item> echo(@RequestBody Mono<Item> item) {
        return item;
    }

    @GetMapping(
        value = "/text",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    Mono<String> text() {
        return Mono.just("Hello WebFlux");
    }

    @GetMapping(
        value = "/binary",
        produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
    )
    Mono<byte[]> binary() {
        byte[] bytes = "BINARY".getBytes(StandardCharsets.UTF_8);
        return Mono.just(bytes);
    }

    @GetMapping(
        value = "/items/stream",
        produces = "application/x-ndjson"
    )
    Flux<Item> stream() {
        return Flux.just(
            new Item(1L, "Keyboard"),
            new Item(2L, "Mouse")
        );
    }

    @GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<String>> events() {
        return Flux.just("connected", "updated")
            .map(value -> ServerSentEvent.builder(value)
                .event("status")
                .build());
    }
}
~~~

Endpoints demonstrated:

- `/items/{id}` returns a Java record serialized by the JSON encoder.
- `/echo` reads a JSON body into Mono<Item> and returns it.
- `/text` returns a String with text/plain.
- `/binary` returns a byte[] with application/octet-stream.
- `/items/stream` returns multiple Items as NDJSON.
- `/events` returns SSE events with text/event-stream.

A real service can replace fixed data with a repository or another publisher. The controller preserves reactive types so WebFlux coordinates reading/writing the body.

### 15.8. Running the Application

In the project directory:

~~~bash
./gradlew bootRun
~~~

Or if Gradle is installed:

~~~bash
gradle bootRun
~~~

Call the endpoints:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/1
curl -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -H "Accept: application/json" -d '{"id":7,"name":"Monitor"}'
curl -i -H "Accept: text/plain" http://localhost:8080/api/text
curl -i -H "Accept: application/octet-stream" http://localhost:8080/api/binary
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/api/items/stream
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/events
~~~

Main response bodies:

JSON:

~~~json
{"id":1,"name":"Keyboard"}
~~~

Text:

~~~text
Hello WebFlux
~~~

Binary:

~~~text
BINARY
~~~

NDJSON:

~~~text
{"id":1,"name":"Keyboard"}
{"id":2,"name":"Mouse"}
~~~

SSE looks like:

~~~text
event:status
data:connected

event:status
data:updated
~~~

Actual output may vary in auxiliary headers or line breaks depending on the server adapter, but the media types and payload semantics must match the declared contracts.

## 16. Testing with WebTestClient and JUnit 5

Create `src/test/java/demo/CodecControllerTest.java`:

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CodecControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void jsonObjectUsesApplicationJson() {
        client.get()
            .uri("/api/items/1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(Item.class)
            .isEqualTo(new Item(1L, "Keyboard"));
    }

    @Test
    void jsonRequestIsDecodedAndEncoded() {
        Item input = new Item(7L, "Monitor");

        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(input)
            .exchange()
            .expectStatus().isOk()
            .expectBody(Item.class)
            .isEqualTo(input);
    }

    @Test
    void stringUsesTextPlain() {
        client.get()
            .uri("/api/text")
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("Hello WebFlux");
    }

    @Test
    void byteArrayUsesOctetStream() {
        byte[] expected = "BINARY".getBytes(StandardCharsets.UTF_8);

        byte[] actual = client.get()
            .uri("/api/binary")
            .accept(MediaType.APPLICATION_OCTET_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_OCTET_STREAM)
            .expectBody(byte[].class)
            .returnResult()
            .getResponseBody();

        assertArrayEquals(expected, actual);
    }

    @Test
    void ndjsonStreamsMultipleObjects() {
        client.get()
            .uri("/api/items/stream")
            .accept(MediaType.parseMediaType("application/x-ndjson"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.parseMediaType("application/x-ndjson"))
            .expectBodyList(Item.class)
            .contains(
                new Item(1L, "Keyboard"),
                new Item(2L, "Mouse")
            );
    }

    @Test
    void unsupportedRequestMediaTypeReturns415() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("not-json")
            .exchange()
            .expectStatus().isEqualTo(415);
    }

    @Test
    void unacceptableResponseMediaTypeReturns406() {
        client.get()
            .uri("/api/items/1")
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isEqualTo(406);
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

These tests verify JSON round-trip, String, binary bytes, NDJSON streams, and both 415/406 content negotiation branches. The tests need no Thread.sleep; WebTestClient awaits responses via reactive exchange and assertions.

SSE can be tested separately using `returnResult(ServerSentEvent.class)`, then consuming the response body stream and asserting event names/data. For infinite streams, apply deliberate timeouts/cancellations instead of waiting for completion.

## 17. Common Pitfalls and Fixes

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Using text/plain for JSON objects | Client treats JSON as plain text | Use application/json |
| Using application/json for arbitrary bytes | Client tries to parse binary as JSON | Use application/octet-stream or a specific file media type |
| Confusing Content-Type with Accept | Server selects the wrong reader/writer or rejects requests | Content-Type describes the request body; Accept describes the desired response |
| Returning a String containing JSON without declaring media type | Client may receive text/plain | Declare application/json or return an object for Jackson to serialize |
| Using byte[] for very large files | Entire file sits on the heap | Use Resource or streaming |
| Using collectList for large streams | Increases RAM and waits for all data | Use Flux with NDJSON/SSE or a streaming protocol |
| Setting maxInMemorySize too high to silence errors | Increases memory pressure risk | Check if streaming is possible, then set controlled limits |
| Reading multipart without limits | Excessive RAM/disk consumption | Limit part count, memory, disk, and file size |
| Consuming DataBuffers manually without releasing | Possible memory leak with pooled buffers | Manage ownership and DataBufferUtils.release |
| Releasing DataBuffers before downstream finishes writing | Corrupted body or runtime errors | Release only when your code owns and has finished consuming it |
| Using NDJSON while the client parses as a JSON array | Client does not understand framing | Agree on application/x-ndjson and parse line by line |
| Using SSE with application/json | Client does not receive proper event framing | Use text/event-stream |
| Ignoring Accept/produces | Can trigger confusing 406 errors | Declare media types and test negotiation |
| Ignoring consumes/Content-Type | Wrongly formatted requests enter decoding | Restrict consumes and handle 415 |
| Writing custom codecs that ignore backpressure | Wastes memory or loses data | Follow Encoder/Decoder and Reactive Streams contracts |
| Creating a new ObjectMapper per request | Increases overhead and causes inconsistent config | Use an ObjectMapper/codec managed in the application context |
| Trusting multipart filenames | Path traversal or writing outside allowed directories | Generate filenames server-side and validate storage paths |
| Logging entire binary or multipart bodies | Bloats logs and risks data exposure | Log metadata, size, media type, and correlation ID |

## 18. Codec and Media Type Selection Checklist

Before implementing an endpoint, determine:

1. Is the body JSON, text, binary, file, form, multipart, or a stream?
2. Does request Content-Type accurately describe the body?
3. Does client Accept match the representation provided by the endpoint?
4. Is the Java type supported by a default codec?
5. Is the body aggregated or streamed element by element?
6. What is the maximum valid payload size?
7. Are maxInMemorySize and multipart limits configured appropriately?
8. If using DataBuffer directly, are ownership and release clear?
9. For streaming, is the framing JSON array, NDJSON, or SSE?
10. Does the client read streaming publishers with bodyToFlux?
11. Is a custom codec genuinely necessary?
12. Have 200, 400, 406, 415, and buffer limit errors been tested appropriately?

| Need | Suggested choice |
| --- | --- |
| REST DTO | application/json + Jackson |
| Plain text | text/plain + String |
| HTML | text/html |
| Small in-memory bytes | application/octet-stream + byte[] |
| Large files | Resource/FilePart streaming |
| Streaming multiple JSON records | application/x-ndjson + Flux<T> |
| Unidirectional event push | text/event-stream + Flux<ServerSentEvent<T>> |
| Form key/value | application/x-www-form-urlencoded |
| Multipart upload | multipart/form-data + FilePart/Part |
| Custom protocol | Custom Encoder/Decoder and reader/writer |

## 19. Self-Check Questions with Answers

**Q1.** How do Content-Type and Accept differ?

**Answer:** Content-Type describes the format of the request body being sent. Accept describes the response format the client can receive.

**Q2.** Are HttpMessageReader and Decoder the same?

**Answer:** No. Decoder converts byte content into objects; HttpMessageReader is an abstraction for reading an HTTP message and typically uses a Decoder internally.

**Q3.** When a controller returns a Java record with application/json, which component serializes the object?

**Answer:** The JSON Encoder used by the HttpMessageWriter compatible with the type and media type.

**Q4.** When should text/plain be used?

**Answer:** When the body is plain text such as a notification message, text content, or strings not represented as JSON/HTML.

**Q5.** Why is byte[] not a good choice for very large files?

**Answer:** The entire content is held in a single byte array on the heap. Resource or streaming allows writing data in chunks.

**Q6.** How does NDJSON differ from a JSON array?

**Answer:** NDJSON contains one JSON document per line, allowing clients to process each record independently. A JSON array is a single document containing all elements.

**Q7.** What is the standard media type for SSE?

**Answer:** text/event-stream.

**Q8.** What does DataBufferLimitException typically indicate?

**Answer:** A codec/reader is aggregating data beyond the configured memory limit. You may need to stream the body or raise the limit in a controlled manner.

**Q9.** Why must DataBuffers be released when consumed manually on Netty?

**Answer:** Some buffers are pooled and reference-counted. Failing to release them promptly can leak native/direct memory.

**Q10.** What do HTTP 415 and 406 typically relate to?

**Answer:** 415 means the request Content-Type is unsupported; 406 means no response representation matches the client's Accept header.

**Q11.** Can WebFlux read a multipart file into a FilePart?

**Answer:** Yes. FilePart provides metadata and a content publisher; it can call transferTo on a target storage reactively.

**Q12.** When is a custom Encoder/Decoder needed?

**Answer:** When a custom format or media type is not supported by default codecs, or specialized conversion behavior is required. Check built-in JSON/String/binary/Resource codecs first.

## 20. Key Takeaways and Official References

- Codecs convert between byte content and Java objects; HTTP readers/writers bind that conversion to requests/responses.
- Content-Type describes the request body; Accept describes the response representation the client accepts.
- JSON uses application/json; plain text uses text/plain; binary uses application/octet-stream or a specific media type.
- Resource suits files; byte[] suits small payloads; DataBuffer is for low-level byte stream processing.
- NDJSON uses application/x-ndjson for line-by-line JSON records; SSE uses text/event-stream.
- Form URL encoded and multipart have dedicated readers and dedicated limits.
- maxInMemorySize protects aggregation operations; increasing the limit must be accompanied by payload controls.
- Pooled DataBuffers must be released according to ownership when consumed directly by the application.
- Use ServerCodecConfigurer/WebFluxConfigurer for the server and WebClient.Builder.codecs for the client.
- Only write custom codecs when default codecs cannot satisfy the contract.

Official references:

1. [Spring Framework Reference — Reactive Core: Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Encoder, Decoder, HttpMessageReader, HttpMessageWriter, DataBuffer, limits, streaming, and custom codecs.
2. [Spring Framework Reference — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): ServerCodecConfigurer and HTTP message codecs configuration.
3. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): codec defaults, CodecConfigurer, CodecCustomizer, and auto-configuration.
4. [Spring Boot 3.5 Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): spring.codec.max-in-memory-size and multipart properties.
5. [Spring Framework Reference — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): client codecs and maxInMemorySize.
6. [Spring Framework Javadoc — ServerCodecConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html): server-side codec configuration API.
7. [Spring Framework Reference — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBuffer lifecycle, pooled buffers, and release.
8. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing HTTP responses, bodies, and content negotiation.
