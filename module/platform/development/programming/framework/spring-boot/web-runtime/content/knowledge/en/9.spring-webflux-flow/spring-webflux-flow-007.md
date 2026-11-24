# HttpMessageReader, HttpMessageWriter, and Codecs in Spring WebFlux

## Learning Objectives

After this lesson, you will be able to:

1. Explain why Spring WebFlux converts between **HTTP byte streams** and **Java values** in the reactive model.
2. Distinguish Spring Core's **Decoder/Encoder** contracts from HTTP-layer **HttpMessageReader/HttpMessageWriter**.
3. Trace how `@RequestBody` is read, how `@ResponseBody` and `ResponseEntity` are written, as well as `bodyToMono`/`bodyToFlux` in WebFlux.fn and `WebClient`.
4. Describe the role of **DataBuffer**, Reactive Streams, backpressure, JSON codecs, String codecs, binary, form/multipart, and Server-Sent Events.
5. Predict reader/writer selection based on Java type, `Content-Type`, `Accept`, `produces`/`consumes`, and distinguish HTTP 400, 406, and 415.
6. Configure default codecs via **ServerCodecConfigurer**, **WebFluxConfigurer**, **CodecCustomizer**, and Spring Boot 3.3 properties.
7. Recognize when streaming is preferable to buffering the full body, and how to manage memory limits and pooled buffer resources.
8. Build a Spring Boot 3.3.x / Java 17+ application demonstrating JSON, text, binary, JSON streaming, SSE, and functional endpoints, and test it with `WebTestClient`.

**Scope:** Spring WebFlux in Spring Framework 6.1.x using Reactor `Mono`/`Flux`, Spring Boot 3.3.x, and Java 17+. Applies to both WebFlux annotated controllers and WebFlux.fn. Spring MVC uses synchronous **`HttpMessageConverter`**s; the classes in this lesson belong to a different pipeline.

## 1. The Problem: HTTP Carries Bytes, Applications Work With Objects

Consider an HTTP request:

~~~http
POST /api/notes HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"Reactive Spring"}
~~~

At the network layer, the HTTP body is bytes delivered to the server. Meanwhile, the controller expects a Java record:

~~~java
public record NoteInput(String title) {}
~~~

The response may be a `Note` DTO:

~~~java
public record Note(long id, String title) {}
~~~

To process this, the server needs to:

- **Decode** the request's JSON bytes into `NoteInput`.
- Run controller and service logic.
- **Encode** `Note` into response JSON bytes.
- Select the appropriate media type and headers so the client understands the payload.

In Spring MVC, the central abstraction is `HttpMessageConverter`, typically operating on `InputStream`/`OutputStream`. **WebFlux** handles non-blocking bodies as **`Publisher<DataBuffer>`**, so it uses readers, writers, and codecs built for Reactive Streams.

High-level overview:

~~~text
HTTP body bytes
  |
  v
Flux<DataBuffer>          // data arrives across buffers
  |
  v
HttpMessageReader
  |
  v
Decoder (Jackson/String/...)
  |
  v
Mono<NoteInput> or Flux<NoteInput>
  |
  v
Controller / service (Publisher<Note>)
  |
  v
HttpMessageWriter
  |
  v
Encoder (Jackson/String/...)
  |
  v
Publisher<DataBuffer>
  |
  v
HTTP response bytes
~~~

This diagram is conceptual: some readers/writers have specialized handling and do not always wrap a single `Encoder` or `Decoder` in the exact same way. The key point is that WebFlux reads and writes bodies as **streams that emit data, completion, error, and cancellation signals**.

## 2. Four Core Concepts

### Encoder<T> — Converts Objects to DataBuffers

`Encoder` lives in package:

~~~java
org.springframework.core.codec.Encoder<T>
~~~

It accepts a `Publisher` of values and produces a `Publisher<DataBuffer>` matching the requested data type and format. Encoding does not necessarily know about a specific HTTP request or response.

For example, `Jackson2JsonEncoder` converts Java `Note` instances into JSON bytes. `StringEncoder` turns strings into bytes according to a charset. Do not assume every `Encoder` can write every media type.

### Decoder<T> — Converts DataBuffers to Objects

`Decoder` lives in:

~~~java
org.springframework.core.codec.Decoder<T>
~~~

It takes a `Publisher<DataBuffer>` and converts it into Java values: a `Mono<T>` for `decodeToMono`, or a `Flux<T>` for multi-item streams when the format allows.

For example, `Jackson2JsonDecoder` uses Jackson to parse JSON into a DTO. For formats containing multiple line-delimited JSON objects, an appropriate codec can emit items one by one instead of buffering everything into one giant JSON string.

### HttpMessageReader<T> — Reads HTTP Bodies

`HttpMessageReader` lives in:

~~~java
org.springframework.http.codec.HttpMessageReader<T>
~~~

It combines reading an HTTP message, headers, media type, and body publisher with decoding into Java types. A common implementation is **DecoderHttpMessageReader**, which wraps a `Decoder`.

Readers handle `@RequestBody`, `@RequestPart`, or calls such as `ServerRequest.bodyToMono` and `WebClient` `response.bodyToMono` (depending on the chosen reader). A reader does not execute business validation or user authorization on its own.

### HttpMessageWriter<T> — Writes HTTP Bodies

`HttpMessageWriter` lives in:

~~~java
org.springframework.http.codec.HttpMessageWriter<T>
~~~

It combines HTTP response headers with encoding Java values into bytes. A common implementation is **EncoderHttpMessageWriter**, which wraps an `Encoder`.

Writers participate in writing `@ResponseBody`, `ResponseEntity<T>`, `ServerResponse.bodyValue`/`body`, `WebClient` `request.bodyValue`/`body`, and streaming responses.

Comparison table:

| Layer | Reading | Writing | HTTP-aware? |
|---|---|---|---|
| Spring Core codec | `Decoder<T>` | `Encoder<T>` | Not necessarily |
| Spring HTTP codec | `HttpMessageReader<T>` | `HttpMessageWriter<T>` | Yes: media type, headers, message |
| WebFlux controller | `@RequestBody`, request argument resolvers | `@ResponseBody`, `ResponseEntity` | MVC-style annotations |
| WebFlux.fn | `ServerRequest.bodyToMono`/`bodyToFlux` | `ServerResponse.bodyValue`/`body` | Functional API |
| WebClient | `ClientResponse.bodyToMono`/`bodyToFlux` | `RequestHeadersSpec.bodyValue`/`body` | HTTP client |

**Do not equate** `HttpMessageReader` with `java.io.Reader` or `HttpMessageWriter` with `java.io.Writer`. They are reactive HTTP body strategies parameterized by Java type and media type.

## 3. DataBuffer and the Role of Reactive Streams

Transport adapters, such as Reactor Netty, deliver request payloads in small chunks over time. Spring uses **DataBuffer** to abstract byte-memory representations such as Netty `ByteBuf` or `java.nio.ByteBuffer`.

A 5 MB body does not necessarily arrive at the application as one contiguous `byte[]`. It can arrive through a `Publisher<DataBuffer>` across many emissions.

~~~text
Network socket
   |
   +---- DataBuffer 1
   +---- DataBuffer 2
   +---- DataBuffer 3
   +---- ... 
   |
   v
Flux<DataBuffer> -> decoder -> Flux<T> / Mono<T>
~~~

Reactive Streams defines how `Publisher` and `Subscriber` communicate via `request(n)`, `onNext`, `onError`, `onComplete`, and `cancel`:

- **Demand/backpressure** lets the consumer signal how much data it is ready to accept.
- **Cancellation** stops the chain when the client disconnects or processing is cancelled.
- **Error signal** propagates parse, I/O, or processing failures.
- **Completion** signals the end of the body or stream.

**Backpressure does not automatically mean infinite or zero memory usage.** A codec that needs to assemble one object from an entire document may have to buffer bytes to parse it. With streaming-friendly formats, a codec can emit items incrementally once enough data arrives.

### DataBuffers Can Be Pooled

Reactor Netty commonly uses reference-counted, pooled buffers. When manipulating `DataBuffer`s directly at a low level, the application must ensure timely release—especially buffers discarded due to filtering, errors, or cancellation.

Spring provides `DataBufferUtils.release(DataBuffer)` and related helpers. Built-in codecs manage resources for you, but when crafting low-level pipelines you must honor ownership contracts. Never release early and continue reading, and never retain buffers indefinitely after a request is cancelled.

Most ordinary REST APIs should return DTOs/records or `Mono`/`Flux` of DTOs and **let Spring's codecs manage `DataBuffer`s** instead of handling raw buffers manually.

## 4. Where Does HttpMessageReader Work in Annotated Controllers?

Entry path with `@RequestBody`:

~~~text
Client sends Content-Type: application/json
        |
        v
Netty/Tomcat reactive adapter
        |
        v
WebFlux HttpHandler -> WebFilter chain
        |
        v
DispatcherHandler
        |
        v
RequestMappingHandlerMapping
        |
        v
RequestMappingHandlerAdapter
        |
        v
Argument resolver for @RequestBody
        |
        +--> Select HttpMessageReader by ResolvableType + Content-Type
                    |
                    +--> Decode body Publisher<DataBuffer>
                    |
                    +--> Mono<NoteInput> or matching Java value
        |
        v
Controller method
~~~

Example:

~~~java
@PostMapping(
    path = "/api/notes",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Note> create(@RequestBody Mono<NoteInput> request) {
    return request.map(input -> new Note(1, input.title()));
}
~~~

This snippet sits inside a controller with appropriate imports and package. Steps:

1. Route and `consumes` conditions are evaluated.
2. Spring inspects parameter type **Mono<NoteInput>**, identifying the body element type as `NoteInput`.
3. Spring selects a reader capable of reading `NoteInput` from `application/json`.
4. The reader/decoder processes the body non-blockingly.
5. The controller receives `Mono<NoteInput>`; code inside `map` runs when the publisher is subscribed, not when the `Mono` is merely created.
6. Once a valid value is decoded, the controller builds the new `Note`.

**Do not call `subscribe()` in the controller.** The WebFlux runtime handles subscription, orchestrates completion, and writes the response. Subscribing manually breaks error/cancellation handling and creates side effects outside the request flow.

### How Do `Mono<T>` and `Flux<T>` Differ?

- **Mono<T>:** at most one value, or empty/error completion; fits a single JSON object or standalone payload.
- **Flux<T>:** multiple values over time; fits framed formats such as NDJSON, SSE, or an item stream.
- **Publisher<DataBuffer>:** low-level byte stream.

Declaring `Flux<T>` alone does not guarantee the response streams every `T` immediately. JSON array formatting, buffering, network/proxies, compression, and clients all affect when bytes arrive.

## 5. HttpMessageWriter Processes Controller Results

Typical outbound path:

~~~text
Controller returns Mono<Note> / Flux<Note>
        |
        v
Return-value handling
        |
        v
Select HttpMessageWriter by Java element type,
Accept, produces, and supported media types
        |
        v
Encoder converts value -> DataBuffer
        |
        v
ServerHttpResponse headers + body
        |
        v
Reactive HTTP server sends bytes
~~~

Example:

~~~java
@GetMapping(
    path = "/api/notes/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Note> find(@PathVariable long id) {
    return Mono.just(new Note(id, "demo"));
}
~~~

With the Jackson JSON codec registered, `Note` is serialized to a JSON object. The body is equivalent to:

~~~json
{"id":5,"title":"demo"}
~~~

for `GET /api/notes/5`. Field order and whitespace in JSON are governed by Jackson configuration; do not claim every environment emits identical byte-for-byte output.

### @RestController and ResponseEntity

In WebFlux, `@RestController` also carries `@ResponseBody` semantics. You can return `Mono<Note>`, `Flux<Note>`, or `Mono<ResponseEntity<Note>>` directly.

~~~java
@PostMapping("/api/items")
public Mono<ResponseEntity<Note>> create(
        @RequestBody Mono<NoteInput> input) {
    return input.map(value ->
            ResponseEntity.status(201)
                    .body(new Note(1, value.title())));
}
~~~

`ResponseEntity` controls **status and headers**; the message writer still determines **how the body is written** when a body is present.

**Note:** When using `ResponseEntity<Mono<T>>` vs. `Mono<ResponseEntity<T>>`, the timing of when headers/status are known differs; Spring Framework supports several reactive return combinations, so pick one clear style and test it to avoid modifying the response after commit.

## 6. Content-Type and Accept: Reader and Writer Look in Opposite Directions

| Header | Sent by | Primary effect |
|---|---|---|
| Request `Content-Type` | Client | Reader picks how to decode the body sent by the client |
| Request `Accept` | Client | Writer picks the response representation acceptable to the client |
| Response `Content-Type` | Server | Tells the client the actual media type returned by the server |
| Response `Content-Length` / `Transfer-Encoding` | Server/transport | Governs body framing on the wire, not DTO decoding rules |

Example:

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Reactive Spring"}
~~~

- The reader inspects `Content-Type: application/json` alongside target type `NoteInput`.
- The writer inspects `Accept: application/json`, `produces` conditions, and type `Note` to choose JSON.
- Request `Content-Type` and Response `Content-Type` do not have to match: a server can accept JSON and return `text/plain` or binary if the endpoint contract specifies it.

### consumes and produces

~~~java
@PostMapping(
    path = "/api/notes",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

- **consumes** restricts the request media types the handler accepts.
- **produces** restricts the media types the handler declares it can produce and interacts with `Accept`.
- A matching reader/writer must still actually support those Java types and media types.

Adding `produces=application/pdf` cannot turn a record into a PDF if PDF generation logic and a suitable writer are missing.

### Commonly Confused Error Statuses

| Scenario | Typical error |
|---|---|
| Malformed JSON request that fails to decode into DTO | 400 Bad Request |
| `required=true` body is missing | 400 Bad Request |
| Validation on decoded body fails | 400 Bad Request (depending on exception handling/config) |
| Client sends `text/plain` while endpoint only `consumes` `application/json` | 415 Unsupported Media Type |
| Client only `Accept`s `text/plain` while endpoint only `produces` `application/json` | 406 Not Acceptable |
| Aggregated body exceeds buffer limit | `DataBufferLimitException`; HTTP status depends on actual config/exception mapping |
| Server fails to encode/write after response commit | Stream may break; cannot guarantee switching to a JSON error body |

**415 relates to input media type; 406 relates to output representation.** Do not blindly try to fix a 406 by changing the request's `Content-Type`, or a 415 by changing `Accept`.

## 7. Which Default Codecs Are Registered?

WebFlux registers codecs according to the framework and libraries on the classpath. There is no single hard-coded list identical for every application.

| Data | Common Reader/Decoder or Writer/Encoder | Typical media types |
|---|---|---|
| JSON objects, JSON arrays | `DecoderHttpMessageReader` + `Jackson2JsonDecoder`; `EncoderHttpMessageWriter` + `Jackson2JsonEncoder` | `application/json`, `application/*+json` |
| NDJSON streams | Jackson JSON codecs with streaming media type | `application/x-ndjson` |
| Plain text | `StringDecoder`, `CharSequenceEncoder`/appropriate String writer | `text/plain` |
| Binary | `ByteArrayDecoder`/`Encoder` or `DataBuffer` codecs | `application/octet-stream` |
| Resource | `ResourceDecoder`/`ResourceHttpMessageWriter` | Matching file/binary media types |
| Form | `FormHttpMessageReader`, `FormHttpMessageWriter` | `application/x-www-form-urlencoded` |
| Multipart | `MultipartHttpMessageReader`, `MultipartHttpMessageWriter`, and part handlers | `multipart/form-data` |
| Server-Sent Events | `ServerSentEventHttpMessageWriter` | `text/event-stream` |
| XML, CBOR, Protobuf, and others | When supporting modules/dependencies and registrations exist | Matching media types |

Implementation names reflect different layers: a **low-level decoder** can be wrapped in an **HTTP message reader**; not every row maps symmetrically to a single class in both directions.

In a standard Spring Boot `starter-webflux` project, the Jackson JSON codec is available through starter-managed dependencies. If required libraries are missing or codec configuration is replaced, endpoints may lose the ability to read or write that media type.

### Is the JSON Codec the Same as Jackson's ObjectMapper?

**ObjectMapper** is the JSON library engine; **Jackson2JsonEncoder/Decoder** integrates Jackson with `DataBuffer` and Reactive Streams; **HttpMessageReader/Writer** integrates the codec with HTTP.

~~~text
Java object / JSON bytes
        ^
        |
  Jackson ObjectMapper
        ^
        |
Jackson2JsonEncoder / Jackson2JsonDecoder
        ^
        |
HTTP message writer / reader
        ^
        |
WebFlux request/response body pipeline
~~~

Changing Jackson configuration affects JSON serialization, but does not directly change `StringDecoder`, the multipart reader, or binary writers.

## 8. Streaming: JSON Array, NDJSON, and SSE Differ

Suppose the server has a `Flux<Note>` emitting three items, 250 ms apart.

### application/json: A Single JSON Document

Typical response:

~~~json
[{"id":1,"title":"n-1"},{"id":2,"title":"n-2"},{"id":3,"title":"n-3"}]
~~~

This is **one JSON array**. A writer can serialize the stream as a collection document, but a client parsing the whole array may not yield results to application code until the entire document finishes. Do not assume three `onNext` signals mean the browser receives three separate JSON objects immediately.

### application/x-ndjson: One JSON Object Per Line

~~~text
{"id":1,"title":"n-1"}
{"id":2,"title":"n-2"}
{"id":3,"title":"n-3"}
~~~

Each line is an independent JSON object. With a streaming NDJSON codec and a streaming client, objects can be processed incrementally as data arrives. There are no square brackets wrapping the entire payload. NDJSON works well for logs, events, and batch item streaming.

### text/event-stream: Server-Sent Events

~~~text
id: 1
event: note
data: {"id":1,"title":"n-1"}

id: 2
event: note
data: {"id":2,"title":"n-2"}

~~~

SSE follows its own framing rules: each event consists of lines such as `id`, `event`, and `data`, separated by a blank line. SSE `data` can be plain text or encoded JSON. Browser `EventSource` can consume events as a stream; parsing JSON inside `data` is up to the client.

**Difference:** NDJSON is a stream of newline-delimited JSON documents; SSE is an event protocol over HTTP. Writing a string containing newlines with `text/event-stream` does not automatically produce a valid SSE event. Use `ServerSentEvent<T>` or a standard SSE writer for proper framing.

### Do Not Equate Flux With End-to-End Streaming

Streaming behavior can be affected by:

- The HTTP message writer and how the encoder flushes.
- Buffers in reverse proxies, CDNs, or gateways.
- HTTP compression and chunking policies.
- Whether the client library calls `bodyToMono` or `bodyToFlux`.
- Response media type and incremental parsing support.
- Timeouts and cancellation.

Always verify with a real client such as `curl -N`, `WebTestClient`, or browser `EventSource`, including testing through any intermediate proxies.

## 9. WebFlux.fn Uses the Same Reader/Writer Infrastructure

WebFlux.fn is the functional routing API: `RouterFunction`, `HandlerFunction`, `ServerRequest`, and `ServerResponse`.

Example:

~~~java
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
        RequestPredicates.POST("/functional/echo"),
        request -> request.bodyToMono(NoteInput.class)
            .flatMap(input -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new Note(1, input.title())))
    );
}
~~~

This snippet should sit in a `@Bean` inside a `@Configuration` or `@SpringBootApplication` class with appropriate imports. `ServerRequest.bodyToMono` uses **message readers** to decode the body. `ServerResponse.bodyValue` uses **message writers** to encode the value.

Thus, **WebFlux codec configuration applies to both annotated controllers and functional endpoints**, despite their different request-handling syntax. Do not mistake WebFlux.fn for a separate web server or a separate codec stack.

## 10. WebClient Is a Reactive HTTP Client That Also Uses Codecs

Not just on the server: **WebClient** reads bodies from remote HTTP responses and encodes bodies it sends in outbound HTTP requests.

~~~text
Server-side WebFlux:
  Incoming HTTP request -> HttpMessageReader -> Java values
  Java values -> HttpMessageWriter -> HTTP response

WebClient:
  Java values -> HttpMessageWriter -> outgoing HTTP request
  Incoming HTTP response -> HttpMessageReader -> Java values
~~~

Example:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("http://localhost:8080")
    .build();

Mono<Note> note = client.get()
    .uri("/api/notes/{id}", 5)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(Note.class);
~~~

This snippet belongs in a component with imports for `WebClient`, `Note`, and `Mono`. Creating the `Mono` does not immediately send the HTTP request; the HTTP request happens when the returned publisher gets a subscriber (for example, WebFlux subscribing to the publisher returned from a handler).

### Avoid Blocking the Event Loop

**Do not** call `.block()` on the WebFlux request path just to turn a `Mono` into a synchronous object. That can stall the event loop, trigger errors, or degrade throughput. When calling downstream APIs, keep the chain reactive with `flatMap`/`map` and appropriate timeouts.

Logical example:

~~~java
Mono<Note> result = client.get()
    .uri("/api/notes/{id}", 5)
    .retrieve()
    .bodyToMono(Note.class)
    .map(note -> new Note(note.id(), note.title().toUpperCase()));
~~~

This describes a data transformation and does not execute the request until subscribed. WebFlux subscribes to the pipeline returned by the controller.

### Server Codecs and Client Codecs Can Have Different Configurations

Spring Boot can customize the `WebClient.Builder` it auto-configures. If you call `WebClient.create()` directly or construct an independent builder, do not assume it inherits Boot's customizations.

When customizing a `WebClient` instance directly, you can use:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs().maxInMemorySize(512 * 1024))
    .build();
~~~

This standalone configuration snippet affects only the `WebClient` instance created from that builder. It does not change server-side readers or writers.

## 11. Configuring Buffer Limits: max-in-memory-size

Some decoders must buffer data to assemble a single object; without a limit, large bodies can consume excessive memory. WebFlux codecs enforce a buffering threshold.

### Common Symptom

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

This error typically occurs when a codec must buffer more than the configured limit (the default for many codecs in Spring Framework is **256 KiB**). Do not assume every request over 256 KiB fails: it depends on the reader, data type, whether streaming or aggregation is used, and configuration.

### Configuring With a Spring Boot 3.3 Property

In `src/main/resources/application.yml`:

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
~~~

Spring Boot 3.3 documents `spring.codec.max-in-memory-size` as the byte limit buffered when aggregating input. It affects the WebFlux server and **auto-configured `WebClient`s**, not arbitrary `WebClient` instances built outside Boot.

This is **not** a general HTTP upload limit, nor does it replace proxy/server request size limits. Raising it to tens of megabytes can spike memory usage under high concurrency. Consider streaming, body size caps, and concurrency limits instead of simply raising the number.

### Configuring Via WebFluxConfigurer

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

This is an **additional configuration class in a WebFlux project**; it compiles with the appropriate `starter-webflux` dependency. It applies to server-side WebFlux codecs. If you already set `spring.codec.max-in-memory-size`, do not also add this configurer just to repeat the same setting.

### Configuring Via CodecCustomizer

Spring Boot 3.3 provides the interface:

~~~java
org.springframework.boot.web.codec.CodecCustomizer
~~~

Example configuration:

~~~java
import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CodecCustomizerConfiguration {

    @Bean
    CodecCustomizer tuneCodecs() {
        return configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(512 * 1024);
    }
}
~~~

This is additional configuration inside a Spring Boot 3.3 project. Spring Boot applies `CodecCustomizer` beans to Boot-configured codecs per its auto-configuration rules. Avoid enabling conflicting customizers and properties simultaneously without knowing application order.

**Version note:** in Spring Boot 4.x, package names and some codec properties changed; these examples are pinned to Boot 3.3 to prevent copying mismatched APIs.

## 12. Configuring Codecs With ServerCodecConfigurer

**ServerCodecConfigurer** exposes codec groups:

- **defaultCodecs():** tunes built-in readers/writers such as Jackson or `maxInMemorySize`.
- **customCodecs():** registers custom readers, writers, encoders, or decoders.
- **getReaders()/getWriters():** returns the final configured lists used by WebFlux.
- **registerDefaults(boolean):** toggles default codecs on or off as needed.

Code example:

~~~java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
~~~

When adding support for a media type like `application/x-custom`:

1. Identify the **Java data types** to read/write.
2. Define the media type clearly.
3. Reuse an existing `Decoder`/`Encoder` or implement a safe one.
4. Optionally wrap the decoder in **`DecoderHttpMessageReader`** and encoder in **`EncoderHttpMessageWriter`**, then register them in `customCodecs()`.
5. Ensure `canDecode`/`canEncode` only return `true` for the exact matching types and media types.
6. Test requests, responses, parse errors, cancellation, and verify other codecs are not hijacked.

If a custom codec claims to support every `Object` and every media type, it can shadow Jackson JSON, String, binary, or `Resource` codecs. Keep custom codecs **narrow and test compatibility**.

### Should You Disable Default Codecs?

Spring Boot docs show:

~~~java
configurer.registerDefaults(false);
~~~

This is a valid statement inside configuration when building a completely bespoke codec list. **Do not use it when merely adding a single codec**: disabling defaults can break JSON, String, multipart, SSE, or binary handling unless you re-register them completely.

### Do Not Add `@EnableWebFlux` Carelessly

Spring Boot auto-configures WebFlux and codecs when the right dependencies are present. To add customization, create a `@Configuration` implementing `WebFluxConfigurer` **without** `@EnableWebFlux`. `@EnableWebFlux` switches you to manual WebFlux configuration and can disable Boot's built-in conveniences.

Similarly, if a project has both `starter-web` and `starter-webflux`, **Spring MVC usually takes precedence by default**. In that case, WebFlux server customizers may not apply to the active server. Inspect the web application type and dependency graph before concluding a codec is broken.

## 13. Jackson Codec: DTOs, Generics, Date/Time, and Security

### ObjectMapper Still Governs JSON Representation

`Jackson2JsonDecoder` and `Jackson2JsonEncoder` rely on `ObjectMapper` and Jackson modules. For example, record:

~~~java
public record Event(long id, String label) {}
~~~

can be encoded as:

~~~json
{"id":2,"label":"demo"}
~~~

Jackson settings such as property naming, serialization inclusion, or `java.time` modules alter how JSON is read and written. Spring Boot offers `spring.jackson.*` properties and Jackson customizers; prefer those instead of replacing the entire codec just to change one JSON rule.

### Generic Types Matter

WebFlux uses **ResolvableType**, not merely raw `Class<?>`, to capture generic element types such as `Mono<List<Event>>` or `Flux<Event>`. Codecs inspect both the Java type and media type before decoding or encoding.

~~~java
Mono<List<Event>> fullList;
Flux<Event> events;
~~~

These are two type declarations, not a runnable program. A complete JSON array usually fits `List<Event>`; a stream of multiple objects like NDJSON fits `Flux<Event>` when a streaming codec supports it.

### Never Serialize Domain Entities Directly

Entities can contain tokens, password hashes, lazy-loading proxies, or cyclic references. The JSON codec applies the active serializer configuration, so define **response DTOs** exposing only public fields. Also enforce request size limits, JSON nesting depth limits, and input validation.

### Do Not Confuse Deserialization Errors With Business Errors

Malformed JSON causes the decoder to emit a `DecodingException` or an error mapped to HTTP 400. Valid JSON with a blank `title` passes decoding and gets rejected by Bean Validation. A valid `title` that conflicts with existing data is a business error handled separately—for instance, as `409 Conflict`.

## 14. Multipart, Forms, File Streaming, and Large Payloads

### Forms

For `application/x-www-form-urlencoded`, WebFlux includes a form-data reader. The functional API can call `ServerRequest.formData()`; annotated handlers can use `@RequestParam` where appropriate.

Do not treat `application/x-www-form-urlencoded` as JSON. Putting `@RequestBody Mono<DTO>` on a form-encoded request will not make Jackson parse form fields into a DTO automatically.

### Multipart

WebFlux provides types like `Part` and `FilePart` along with multipart codecs. You can bind part metadata with `@RequestPart` and uploaded files with `FilePart`:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    return file.transferTo(
            java.nio.file.Path.of("/tmp/received-file.bin")
    ).thenReturn("uploaded");
}
~~~

This is an **illustrative snippet** inside a `@RestController` with appropriate imports; it assumes the path is valid/writable and two concurrent requests do not write the same file. Never use a client-supplied filename directly as a storage path; production apps need safe generated filenames, MIME/size checks, permission checks, and storage policies.

For large multipart streams, WebFlux also supports **`Flux<PartEvent>`**, enabling part-by-part processing without buffering the whole multipart payload. Release `DataBuffer`s per contract if handling individual events manually.

### Distinguishing Codec vs. Multipart Memory Limits

Spring Boot 3.3 exposes distinct properties, for example:

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
  webflux:
    multipart:
      max-in-memory-size: 256KB
      max-disk-usage-per-part: 10MB
      max-parts: 20
~~~

These are **illustrative values** to tune per real requirements. `spring.codec.max-in-memory-size` controls buffering when codecs aggregate input; `spring.webflux.multipart.*` properties govern limits specific to the multipart reader. Do not expect changing one property to override every other limit.

In production, reverse-proxy, gateway, transport, and storage quota limits are typically needed as well.

## 15. Complete Example: JSON, Text, Bytes, NDJSON, SSE, and Functional Route

This hands-on section uses Spring Boot 3.3.x, Java 17+, `starter-webflux`, and Reactor Netty. Every controller example uses WebFlux APIs; no Servlet, `DispatcherServlet`, or `HttpMessageConverter` is used.

### 15.1. Dependencies

In a Gradle Spring Boot project with plugin and repositories configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is only the `dependencies` block of `build.gradle`. Do not add `spring-boot-starter-web` to this practice project, because when both starters are present Boot defaults to MVC instead of WebFlux.

### 15.2. Java Application

Create **src/main/java/com/example/webfluxcodec/CodecLessonApplication.java**:

~~~java
package com.example.webfluxcodec;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.http.codec.ServerSentEvent;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class CodecLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecLessonApplication.class, args);
    }

    public record NoteInput(String title) {}
    public record Note(long id, String title) {}

    @RestController
    static class NoteController {

        private final AtomicLong ids = new AtomicLong();

        @PostMapping(
                path = "/api/notes",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        @ResponseStatus(HttpStatus.CREATED)
        Mono<Note> create(@RequestBody Mono<NoteInput> body) {
            return body.map(input ->
                    new Note(ids.incrementAndGet(), input.title()));
        }

        @GetMapping(
                path = "/api/notes/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<Note> get(@PathVariable long id) {
            return Mono.just(new Note(id, "sample-" + id));
        }

        @PostMapping(
                path = "/api/text",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        Mono<String> text(@RequestBody Mono<String> body) {
            return body.map(String::toUpperCase);
        }

        @GetMapping(
                path = "/api/bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        Mono<byte[]> bytes() {
            return Mono.just(
                    "ABC".getBytes(StandardCharsets.US_ASCII));
        }

        @GetMapping(
                path = "/api/notes/ndjson",
                produces = MediaType.APPLICATION_NDJSON_VALUE
        )
        Flux<Note> ndjson() {
            return Flux.range(1, 3)
                    .delayElements(Duration.ofMillis(250))
                    .map(i -> new Note(i, "stream-" + i));
        }

        @GetMapping(
                path = "/api/notes/sse",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE
        )
        Flux<ServerSentEvent<Note>> sse() {
            return Flux.range(1, 3)
                    .delayElements(Duration.ofMillis(250))
                    .map(i -> ServerSentEvent.<Note>builder()
                            .id(Integer.toString(i))
                            .event("note")
                            .data(new Note(i, "stream-" + i))
                            .build());
        }
    }

    @Bean
    RouterFunction<ServerResponse> functionalRoute() {
        return RouterFunctions.route(
                RequestPredicates.POST("/functional/echo"),
                request -> request.bodyToMono(NoteInput.class)
                        .flatMap(input -> ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new Note(100, input.title())))
        );
    }
}
~~~

**Explanation:**

- `@RestController` uses WebFlux's annotation handler adapter; JSON bodies flow through reactive readers and writers, not `HttpMessageConverter`.
- `POST /api/notes` accepts `Mono<NoteInput>` and produces `Mono<Note>`. Valid JSON is decoded into `NoteInput` by Jackson.
- `GET /api/notes/{id}` is an illustrative endpoint creating a `Note` from the supplied `id`; **there is no database**, so do not treat this as real CRUD storage.
- `POST /api/text` uses the String codec to read/write `text/plain`; `String::toUpperCase` uses the default locale, so tests stick to simple ASCII.
- `GET /api/bytes` returns three ASCII bytes `A`, `B`, `C` as `application/octet-stream`.
- `GET /api/notes/ndjson` returns multiple `Note`s as an NDJSON stream.
- `GET /api/notes/sse` returns SSE events with `id`/`event`/`data` framed by the SSE writer.
- `functionalRoute` shows `ServerRequest.bodyToMono` and `ServerResponse.bodyValue` using the same WebFlux codecs.
- `Flux.range` and `delayElements` form an in-memory source, not real network I/O. In production, use reactive repositories/clients and avoid blocking the event loop.

**Execution scope:** this is a complete Java source file within a **Spring Boot 3.3.x project having `starter-webflux`**; do not compile with standalone `javac` without the Spring/Reactor/Jackson classpath.

### 15.3. Configuring application.yml

Create **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  codec:
    max-in-memory-size: 512KB
~~~

This is an illustrative buffer size. With finite NDJSON/SSE responses, the goal is letting learners observe streaming. You do not need to register a JSON codec manually when `starter-webflux` already auto-configures Jackson.

### 15.4. Running the Application

In the Gradle project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 15.5. Testing JSON Request/Response

On Linux/macOS:

~~~bash
curl -i -X POST http://localhost:8080/api/notes \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Reactive Spring"}'
~~~

Typical response for the first request:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":1,"title":"Reactive Spring"}
~~~

Status 201 comes from `@ResponseStatus(CREATED)`. The ID is 1 for the first creation request in a fresh process; subsequent calls increment `id`. Header order and JSON field order may vary.

On Windows PowerShell, to avoid JSON quoting differences across PowerShell versions, create a **note.json** file containing:

~~~json
{"title":"Reactive Spring"}
~~~

and run:

~~~powershell
curl.exe -i -X POST http://localhost:8080/api/notes -H "Content-Type: application/json" -H "Accept: application/json" --data-binary "@note.json"
~~~

In the same environment, test GET:

~~~bash
curl -s http://localhost:8080/api/notes/5
~~~

Equivalent body:

~~~json
{"id":5,"title":"sample-5"}
~~~

### 15.6. Testing Text and Binary

Text:

~~~bash
curl -s -X POST http://localhost:8080/api/text \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data 'hello'
~~~

Exact body for this ASCII example:

~~~text
HELLO
~~~

Binary:

~~~bash
curl -s http://localhost:8080/api/bytes
~~~

Body consists of bytes `0x41 0x42 0x43`, matching ASCII:

~~~text
ABC
~~~

When testing binary payloads in real applications, write output to a file and compare size/hashes rather than printing non-text data to the terminal.

### 15.7. Testing NDJSON and SSE

NDJSON:

~~~bash
curl -N -H 'Accept: application/x-ndjson' \
  http://localhost:8080/api/notes/ndjson
~~~

Equivalent payload:

~~~text
{"id":1,"title":"stream-1"}
{"id":2,"title":"stream-2"}
{"id":3,"title":"stream-3"}
~~~

SSE:

~~~bash
curl -N -H 'Accept: text/event-stream' \
  http://localhost:8080/api/notes/sse
~~~

Output takes the form:

~~~text
id:1
event:note
data:{"id":1,"title":"stream-1"}

id:2
event:note
data:{"id":2,"title":"stream-2"}

id:3
event:note
data:{"id":3,"title":"stream-3"}

~~~

Whitespace after colons, line ordering, and frame flushing can vary by serializer and version. The key assertion is **three events carrying `id`/`event`/`data` and valid JSON payloads**.

Functional route:

~~~bash
curl -s -X POST http://localhost:8080/functional/echo \
  -H 'Content-Type: application/json' \
  --data '{"title":"function"}'
~~~

Equivalent body:

~~~json
{"id":100,"title":"function"}
~~~

## 16. Testing WebFlux Codecs With WebTestClient

Add tests to **src/test/java/com/example/webfluxcodec/CodecLessonApplicationTests.java**:

~~~java
package com.example.webfluxcodec;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class CodecLessonApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void jsonBodyIsDecodedAndEncoded() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "demo"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.title").isEqualTo("demo");
    }

    @Test
    void rejectsRequestMediaTypeOtherThanJson() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isEqualTo(
                        HttpStatus.UNSUPPORTED_MEDIA_TYPE);
    }

    @Test
    void rejectsUnacceptableResponseType() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_PLAIN)
                .bodyValue(Map.of("title", "demo"))
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.NOT_ACCEPTABLE);
    }

    @Test
    void badJsonGetsBadRequest() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{bad-json")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void textIsUppercased() {
        client.post()
                .uri("/api/text")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("HELLO");
    }

    @Test
    void ndjsonResponseHasStreamingMediaType() {
        client.get()
                .uri("/api/notes/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON);
    }
}
~~~

Spring Boot project using Gradle wrapper:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The tests verify: JSON reader and writer, text reader/writer, 415, 406, 400, and NDJSON `Content-Type`. They validate real WebFlux behavior rather than guessing codec classes by name.

**Test scope:** `WebTestClient` with `WebEnvironment.RANDOM_PORT` executes HTTP requests against a live embedded server. Using `bindToController` or `bindToApplicationContext` does not open a TCP socket; both approaches are useful but exercise different layers.

Do not depend on JSON field ordering or response whitespace. For long-lived SSE streams, use `WebTestClient.returnResult(...).getResponseBody()` with `StepVerifier` and a timeout to assert individual events and cancellation without letting tests hang forever.

## 17. Interpreting 400/406/415 Errors in WebFlux

### 400 Bad Request

Common causes:

- Malformed JSON.
- Field type mismatch with the target DTO.
- Required body missing.
- Bean Validation failure on the decoded value.

Example:

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json

{bad-json
~~~

The Jackson decoder cannot parse the syntax, so WebFlux handles the body-reading error and typically returns HTTP 400. The exact error body depends on the error handler and Boot configuration; avoid hard-coding it in tests.

### 415 Unsupported Media Type

~~~http
POST /api/notes HTTP/1.1
Content-Type: text/plain

hello
~~~

The endpoint only `consumes` `application/json`. Either the handler rejects that representation or no reader can decode the target type from `text/plain`; HTTP 415 is the expected response.

### 406 Not Acceptable

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json
Accept: text/plain

{"title":"ok"}
~~~

The endpoint only `produces` `application/json`. Since the client only accepts `text/plain`, the server cannot pick a compatible representation and returns 406.

### Buffer Limits and DataBufferLimitException

If a JSON request exceeds what a codec is permitted to aggregate, `DataBufferLimitException` can occur. Do not assume the default status is always 413; the actual status depends on exception mapping, codecs, framework behavior, and commit state. When you need a dedicated API contract for oversized bodies, configure limits at the gateway/server along with an appropriate exception handler.

### Encoding Errors

Serialization can fail when a DTO getter throws an exception, data cannot be serialized to JSON, or cyclic references exist. Once a response has partially streamed, it is not always possible to change status/body for the whole response. Monitor server logs and client-side error signals.

## 18. Readers/Writers Do Not Replace Validation and Business Logic

Codecs only bridge **wire representation** and **Java data**; they do not handle:

- Authentication/authorization.
- Database transactions and persistence.
- Business invariants such as inventory, payments, or workflow state.
- Rate limiting or abuse prevention.
- Sensitive-data filtering policies.
- Downstream service timeouts.

When using Bean Validation:

~~~java
public record CreateInput(
        @jakarta.validation.constraints.NotBlank String title
) {}
~~~

Used with `@Valid @RequestBody Mono<CreateInput>` and the `spring-boot-starter-validation` dependency, the framework can validate constraints after decoding. Validation exceptions in WebFlux can be `WebExchangeBindException` or `HandlerMethodValidationException` depending on constraint placement and controller method signature.

Do not confuse **successful decoding** with **valid business input**.

## 19. Inspecting Readers/Writers at Runtime

When debugging confusing behavior, you can inspect the reader/writer lists of a configured `ServerCodecConfigurer`. Illustrative snippet inside WebFlux configuration:

~~~java
import org.springframework.http.codec.ServerCodecConfigurer;

ServerCodecConfigurer configurer = ServerCodecConfigurer.create();
System.out.println(configurer.getReaders().size());
System.out.println(configurer.getWriters().size());
~~~

This is an **illustrative API snippet**, not code that directly inspects the active context's codec registry. A freshly constructed configurer does not necessarily include Spring Boot's customizers, because Boot applies properties and bean customizations separately.

To inspect the running app's registry, examine the codec configuration actually used by the framework or debug `ServerCodecConfigurer`, `WebFluxConfigurer`, and `CodecCustomizer` beans. Printing a brand-new configurer's codec list and assuming it matches Boot's runtime configuration can mislead diagnostics.

### Logs and Metrics

Consider tracking:

- Request `Content-Type`, `Accept`, and response `Content-Type`.
- Target Java type and return type.
- Route `consumes`/`produces` conditions.
- Which codec reads/writes during trace/debug sessions.
- Decode/encode errors and root causes.
- 400/406/415 counts, p95 latency, and memory usage.
- Concurrent request counts and active streaming responses.

Do not leave sensitive body logging or `DEBUG`/`TRACE` enabled indefinitely in production. The `spring.codec.log-request-details` property controls logging of codec request details (which may include form data or headers), so enforce an appropriate logging policy.

## 20. Common Mistakes

| Misconception | Reality |
|---|---|
| WebFlux uses `HttpMessageConverter` just like Spring MVC | WebFlux uses `HttpMessageReader`/`Writer` and reactive codecs |
| `Decoder`/`Encoder` are identical to `Reader`/`Writer` | `Reader`/`Writer` add HTTP context and media type handling |
| Returning `Flux` guarantees streaming item by item to the client | Writers, media types, proxies, and clients may buffer |
| Raising `maxInMemorySize` is the only way to handle large bodies | Use streaming, limits, multipart/file paths instead |
| The JSON codec validates business rules | Decoders only read representations; validation/services enforce rules |
| `ResponseEntity` eliminates the need for writers | The body inside `ResponseEntity` still must be encoded |
| `WebClient` creating a `Mono` already sent the HTTP request | Reactive requests execute upon subscription |
| Calling `block()` on the WebFlux event loop is convenient and safe | Can stall/break throughput; keep the pipeline non-blocking |
| Using request `Content-Type` to ask for a JSON response | `Accept` expresses response preference |
| `@EnableWebFlux` is always required to customize codecs | `WebFluxConfigurer` in Boot usually needs no `@EnableWebFlux` |
| `registerDefaults(false)` just adds one codec | It removes defaults, potentially breaking JSON/String/SSE |
| Server codec configuration automatically applies to every standalone `WebClient` | Distinguish Boot's auto-configured builder from custom clients |
| `DataBuffer`s are auto-released when stored in a collection | Pooled buffers require clear ownership and cleanup per contract |

## 21. Step-by-Step Diagnostic Procedure

When an endpoint returns the wrong media type or fails to decode:

1. **Check the active stack:** did Boot pick `REACTIVE` or `SERVLET`? If both `starter-web` and `starter-webflux` exist, MVC is the default.
2. **Check the route:** do path, method, `consumes`, and `produces` match the request?
3. **Check `Content-Type` and `Accept`:** did headers arriving behind any proxy match what the client sent?
4. **Check the Java type:** is `@RequestBody` `NoteInput`, `Mono<NoteInput>`, `Flux<NoteInput>`, or `String`? Is the writer receiving a DTO, `Mono`, `Flux`, `Resource`, or `byte[]`?
5. **Check the registry:** are Jackson/String/multipart/SSE codecs still registered? Is an overly broad custom codec or `registerDefaults(false)` interfering?
6. **Check the exact failure:** malformed body (400), input media type (415), output negotiation (406), buffer limit, or serialization exception.
7. **Check streaming:** response `Content-Type`, whether the codec flushes per item, whether proxies buffer, and whether the client uses `bodyToFlux` vs. buffering everything with `bodyToMono`.
8. **Check resources:** are pooled `DataBuffer`s leaking, prefetch values too high, or manual subscriptions running outside the lifecycle?
9. **Check tests:** add `WebTestClient` tests for status/body/media type; use `StepVerifier` to verify emissions and cancellation.

Avoid blindly raising memory limits indefinitely or disabling default codecs before identifying the actual cause.

## 22. Self-Check Questions

**Question 1.** Do `Decoder` and `HttpMessageReader` have the exact same responsibility?

**Answer:** Not completely. `Decoder` converts `DataBuffer`s into Java values at a lower level; `HttpMessageReader` integrates decoding with HTTP headers, media types, and message bodies.

**Question 2.** A controller returns `Flux<Note>` with `produces=application/json`. Does that guarantee the client receives each `Note` like NDJSON?

**Answer:** No. JSON array and NDJSON have different representations; `Flux` alone does not decide framing or flushing. To emit independent JSON objects line by line, choose `application/x-ndjson` with supporting codecs and clients.

**Question 3.** A client sends valid JSON with `Content-Type=text/plain` to an endpoint that only consumes JSON. Typical error?

**Answer:** `415 Unsupported Media Type`, because the declared media type does not match the endpoint contract.

**Question 4.** To change response formatting, should you replace the Reader or Writer?

**Answer:** `Writer`/`Encoder` handles response bodies; `Reader`/`Decoder` handles request bodies. A custom codec can provide both if a format must be read and written.

**Question 5.** Why can setting `spring.codec.max-in-memory-size` to 50 MB for every endpoint be dangerous?

**Answer:** Under concurrent requests requiring aggregation, total buffered memory can spike sharply. Prefer streaming, size limits, and concurrency caps.

**Question 6.** Why can a manually constructed `WebClient.builder().build()` behave differently from a Boot-injected builder?

**Answer:** Boot's customizers and properties are applied through auto-configuration. A directly constructed builder does not automatically receive them unless explicitly configured.

**Question 7.** Should you manually call `subscribe()` to "run faster" inside a `@RestController`?

**Answer:** No. The WebFlux runtime manages subscription and cancellation for the response pipeline; subscribing manually detaches side effects from the request lifecycle.

**Question 8.** Is an SSE response just a regular JSON array?

**Answer:** No. SSE uses `id`/`event`/`data` framing and blank lines between events. `data` fields may carry JSON, yet the overall response is not a JSON array.

**Question 9.** Why might a `DataBuffer` skipped in a filter require cleanup?

**Answer:** Buffers may be pooled and reference-counted. When a custom pipeline takes ownership and drops a buffer, it must release it per contract to prevent resource leaks.

**Question 10.** When a project has both `starter-web` and `starter-webflux`, would you tune WebFlux `CodecCustomizer` first or check the active stack?

**Answer:** Determine the web application type first. Boot normally chooses Spring MVC when both starters are present; WebFlux server codecs may not even sit on the live request path.

## 23. Implementation Checklist

- [ ] Confirmed the app actually runs WebFlux on the intended web stack.
- [ ] Request `Content-Type` and response `Accept`/`produces` specify media types clearly.
- [ ] Public DTOs/records and JSON serialization are controlled, never exposing sensitive entities.
- [ ] `Mono<T>` chosen for single items; `Flux<T>` chosen for multi-item or true streaming payloads.
- [ ] JSON array, NDJSON, and SSE clearly distinguished in API contracts.
- [ ] Reasonable `max-in-memory-size` and request/multipart limits configured.
- [ ] No manual `block()`/`subscribe()` in the request path unless specifically isolated and controlled.
- [ ] Custom codecs restrict supported types/media types narrowly and preserve default codecs unless intentional.
- [ ] Server-side WebFlux codec config distinguished from custom `WebClient` instances.
- [ ] Tests cover 400, 406, 415, JSON/text/binary, and streaming media types.
- [ ] When handling raw `DataBuffer`s, release/cancel/error contracts are honored.
- [ ] Proxies and clients tested for end-to-end streaming when required.
- [ ] API docs and logging/metrics exist to diagnose decode and encode failures.

## References

- [Spring Boot 3.3 — Reactive Web Applications: HTTP Codecs with HttpMessageReaders and HttpMessageWriters](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Boot 3.3 — Common Application Properties (`spring.codec.*`, `spring.webflux.multipart.*`)](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
