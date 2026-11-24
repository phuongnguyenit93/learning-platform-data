# Decoding a Single Object vs. Decoding a Sequence of Objects in Spring WebFlux

In Spring WebFlux, incoming HTTP data arrives as bytes split into multiple chunks. Before a controller or WebClient receives a Java object, a **codec** must read the bytes, recognize the format, decode them, and convert them into the data type requested by the application.

The key point of this lesson is distinguishing two goals:

- **Decoding a single value:** a body is converted into one Java object, typically represented by **Mono<T>**.
- **Decoding a sequence of values:** a body is read into multiple Java objects, typically represented by **Flux<T>**.

The difference is not just Mono vs. Flux. It also depends on the target Java type, the wire data structure, the media type, the codec's streaming capability, and memory limits. For example, the same JSON array can be read as **Mono<List<Event>>** (a single value representing the whole list) or **Flux<Event>** (multiple separate Event values).

This lesson belongs to the **Codecs and Buffers** module, focusing on how WebFlux decodes an object vs. a sequence, how a JSON array differs from NDJSON, the role of DataBuffer, and how to control memory.

## 1. Learning Objectives

After this lesson, you can:

- Explain the roles of Encoder, Decoder, HttpMessageReader, and HttpMessageWriter.
- Distinguish decoding a single object from decoding a stream of objects.
- Choose Mono<T>, Mono<List<T>>, or Flux<T> according to the desired cardinality.
- Understand JSON object, JSON array, and NDJSON as three distinct payload shapes.
- Describe how Jackson2JsonDecoder emits elements when decoding a Flux.
- Understand why one DataBuffer does not correspond to one JSON object or one record.
- Use WebClient bodyToMono and bodyToFlux with the right types.
- Return a Flux under application/json or application/x-ndjson according to the required semantics.
- Manage maxInMemorySize, DataBufferLimitException, and pooled DataBuffers.
- Write a Java 17+ application and test it with WebTestClient.

## 2. The Big Picture: From Bytes to Objects

An HTTP request body does not arrive at the application as a Java object. The server receives bytes from the network; WebFlux passes them through a message reader and codec before the handler method processes the data.

~~~text
HTTP request body
       |
       v
Network byte chunks
       |
       v
DataBuffer stream
       |
       v
HttpMessageReader
       |
       v
Decoder / Codec
       |
       +------------------------------+
       |                              |
       v                              v
Single Java value                Multiple Java values
Mono<T>                         Flux<T>
       |                              |
       v                              v
Controller / WebClient consumer
~~~

The classes have distinct responsibilities:

- **DataBuffer:** represents a region of bytes. It can wrap a regular byte buffer or a buffer pooled by a server such as Reactor Netty.
- **Decoder<T>:** low-level contract converting a Publisher<DataBuffer> into a publisher of type T.
- **HttpMessageReader<T>:** integrates decoding with HTTP messages, media types, headers, and hints.
- **HttpMessageWriter<T>:** writes Java values to an HTTP body via an encoder.
- **Encoder<T>:** converts a publisher of T into a DataBuffer stream.
- **Codec:** a general term for an encode/decode component; in WebFlux this is typically a reader/writer or encoder/decoder pair.

On the server side, @RequestBody is handled by configured HttpMessageReaders. On the client side, WebClient uses similar codecs to decode responses and encode requests. Thus, the same format can be handled consistently on both sides.

## 3. A Single Object: Mono<T>

When the application expects exactly one object, the appropriate reactive type is usually **Mono<T>**.

Example JSON payload:

~~~json
{
  "id": "evt-1",
  "sequence": 1
}
~~~

Java type:

~~~java
public record Event(String id, int sequence) {
}
~~~

Controller can accept:

~~~java
@PostMapping("/events/one")
public Mono<Event> receiveOne(@RequestBody Mono<Event> body) {
    return body;
}
~~~

WebFlux reads the body, picks the reader matching application/json, and the decoder turns the document into an Event. The publisher emits at most one Event and completes.

On the WebClient side:

~~~java
Mono<Event> event = webClient.get()
    .uri("/events/evt-1")
    .retrieve()
    .bodyToMono(Event.class);
~~~

bodyToMono(Event.class) tells WebClient that the expected response is a single Event value. The target type helps the codec choose the appropriate decoding strategy.

### One Object Does Not Mean One DataBuffer

A JSON object can arrive across multiple DataBuffers:

~~~text
DataBuffer #1: {"id":"ev
DataBuffer #2: t-1","seq
DataBuffer #3: uence":1}
                  |
                  v
       Decoder maintains parse state
                  |
                  v
             Event(...)
~~~

Buffer boundaries are determined by the network and server. A single JSON object may be split across two buffers; conversely, one buffer may hold multiple parts of a document or multiple records. Never assume each onNext(DataBuffer) corresponds to one complete object.

The Decoder must maintain parse state across buffers until enough bytes arrive to construct a value. With Jackson's non-blocking parser, this can happen without aggregating the entire response into a String first.

## 4. A List as a Single Value: Mono<List<T>>

There is an easy-to-confuse case: the application receives a JSON array but wants to treat **the entire list as a single value**.

Payload:

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2}
]
~~~

Target type:

~~~java
Mono<List<Event>>
~~~

Controller:

~~~java
@PostMapping("/events/array-as-list")
public Mono<List<Event>> receiveArrayAsList(
        @RequestBody Mono<List<Event>> body) {
    return body;
}
~~~

Mono emits one List object containing two Events. The handler receives the list after the codec decodes the array structure into a collection. This suits business logic that must process the whole batch as one unit, such as checking total item count, validating whole-list consistency, or performing a batch operation.

WebClient can read the same payload using a generic type:

~~~java
Mono<List<Event>> events = webClient.get()
    .uri("/events/array")
    .retrieve()
    .bodyToMono(new ParameterizedTypeReference<List<Event>>() {});
~~~

Due to Java type erasure, when passing generic types like List<Event>, use ParameterizedTypeReference to preserve type information for the codec. List.class alone does not tell the codec that the inner elements are Events.

### Mono<List<T>> vs. Flux<T> Differ in Cardinality

| Type | Emitted signals | Value per signal |
| --- | --- | --- |
| Mono<Event> | 0 or 1 | One Event |
| Mono<List<Event>> | 0 or 1 | One List containing multiple Events |
| Flux<Event> | 0 to many | Each signal is one Event |

Mono<List<Event>> is still a single-value publisher. Flux<Event> is a multi-value publisher. Although both types can read the same JSON array, how controllers/services receive and process the data differs.

## 5. A Sequence of Objects: Flux<T>

When you want to process each object individually, use **Flux<T>**.

~~~java
@PostMapping("/events/array-as-flux")
public Flux<Event> receiveArrayAsFlux(
        @RequestBody Flux<Event> body) {
    return body;
}
~~~

With Spring's Jackson JSON decoder, when the target type is Flux, the parser can emit each object as soon as enough bytes arrive to complete that object. The input content can be a JSON array or a line-delimited JSON format such as NDJSON.

WebClient reading a sequence of objects:

~~~java
Flux<Event> events = webClient.get()
    .uri("/events/stream")
    .accept(MediaType.valueOf("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Event.class);
~~~

Each element of the Flux is an Event. Consumers can process elements individually using map, flatMap, concatMap, buffer, or by writing to an appropriate sink.

~~~java
Flux<Event> saved = events.concatMap(repository::save);
~~~

concatMap preserves ordering and waits for saving the current element to complete before moving to the next. If business logic permits parallel processing, you can use flatMap with a deliberately bounded concurrency.

**Do not assume Flux means infinite data.** A Flux can emit 0 elements, 1 element, or millions of elements and then complete. The difference lies in cardinality and consumption style, not whether the stream must last forever.

## 6. JSON Object, JSON Array, and NDJSON

To decode one or multiple objects, you must first understand the payload structure on the wire.

### JSON Object: One Document with a Root Object

~~~json
{"id":"evt-1","sequence":1}
~~~

This is a JSON document containing one object. It is typically decoded into Mono<Event>.

### JSON Array: One Document Containing Multiple Objects

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2}
]
~~~

This is still **one JSON document**, whose root is an array. The codec can:

- Decode into one List inside Mono<List<Event>>.
- Decode into individual elements inside Flux<Event> if the decoder supports streaming arrays.

The second point is very useful: a JSON array does not necessarily have to be converted into one large List before the controller can receive the first element. The Jackson non-blocking decoder can emit each object as soon as that object is complete.

### NDJSON: Multiple JSON Documents Delimited by Newlines

NDJSON (Newline Delimited JSON, typically using media type application/x-ndjson) looks like:

~~~text
{"id":"evt-1","sequence":1}
{"id":"evt-2","sequence":2}
{"id":"evt-3","sequence":3}
~~~

Each line is an independent JSON value. This format fits streams well because the receiver can parse a record as soon as its line completes while subsequent records are still in transit.

NDJSON is not a JSON array. The three lines above together do not form a single valid JSON document if simply joined by newlines. Client and server must agree on the media type and framing rules.

### Payload Comparison

| Format | Shape example | Meaning | Common usage |
| --- | --- | --- | --- |
| JSON object | {...} | One document, one object | Mono<T> |
| JSON array | [{...},{...}] | One document, multiple objects | Mono<List<T>> or Flux<T> |
| NDJSON | One JSON value per line | Multiple JSON values delimited by newlines | Streaming Flux<T> |

Never send adjacent JSON objects arbitrarily like {"id":"a"}{"id":"b"} without explicit framing. Use a JSON array, NDJSON, or a defined sequence protocol.

## 7. Decoder.decodeToMono and Decoder.decode

At the Spring Core layer, the **Decoder<T>** interface describes how to convert a byte stream into an object stream. The two key methods are:

~~~java
Mono<T> decodeToMono(
    Publisher<DataBuffer> input,
    ResolvableType elementType,
    MimeType mimeType,
    Map<String, Object> hints);

Flux<T> decode(
    Publisher<DataBuffer> input,
    ResolvableType elementType,
    MimeType mimeType,
    Map<String, Object> hints);
~~~

Meaning:

- **decodeToMono:** decodes input into at most one value of T. The decoder may have to buffer enough bytes to build one complete value.
- **decode:** decodes input into a Flux<T>, potentially emitting each value as soon as enough data arrives for one element.

Both APIs accept ResolvableType instead of just Class because the target type can be generic such as List<Event>. MimeType helps the decoder pick the right format; hints pass additional context to the decoding process.

This is a low-level codec contract, independent of HTTP. A decoder may also provide a method to decode a single DataBuffer already containing an entire message, suited for formats where each message is pre-framed.

### HttpMessageReader at the HTTP Layer

WebFlux uses **HttpMessageReader<T>** to read HTTP content. The main methods correspond to the two cardinalities:

~~~java
Mono<T> readMono(
    ResolvableType elementType,
    ReactiveHttpInputMessage message,
    Map<String, Object> hints);

Flux<T> read(
    ResolvableType elementType,
    ReactiveHttpInputMessage message,
    Map<String, Object> hints);
~~~

HttpMessageReader can also check canRead(elementType, mediaType) and advertise its supported media types. Therefore, WebFlux can select a reader based on the handler parameter type and the request's Content-Type.

Normally applications do not call decodeToMono or readMono directly. When declaring @RequestBody Mono<T>, @RequestBody Flux<T>, or calling WebClient bodyToMono/bodyToFlux, the framework selects the appropriate reader/decoder automatically.

### Relationship Diagram

~~~text
@RequestBody Mono<T> / WebClient.bodyToMono(T)
                  |
                  v
          HttpMessageReader.readMono
                  |
                  v
          Decoder.decodeToMono
                  |
                  v
                Mono<T>


@RequestBody Flux<T> / WebClient.bodyToFlux(T)
                  |
                  v
           HttpMessageReader.read
                  |
                  v
             Decoder.decode
                  |
                  v
                Flux<T>
~~~

Similarly on the write side, HttpMessageWriter uses Encoder to turn a publisher of objects into DataBuffers and write them to the response/request body.

## 8. How Does Jackson JSON Decode an Object vs. a Sequence?

When Jackson is present, WebFlux provides a JSON decoder built on a non-blocking parser. In Spring Framework 6.x, the commonly used class is **Jackson2JsonDecoder**.

General workflow:

1. The parser receives DataBuffers incrementally.
2. The parser maintains state across byte chunks and builds a token buffer for a complete JSON value.
3. ObjectMapper converts the token buffer into the target Java type.
4. For a single-value target type like Mono, the decoder produces one value.
5. For a multi-value target type like Flux, the decoder can emit each object as soon as enough bytes are received to decode that object.

The input to Flux can be a JSON array or a line-delimited format like NDJSON/JSON Lines. Thus, a JSON array can be decoded into individual Flux elements without necessarily building a List first.

### Reading One Object

With payload:

~~~json
{"id":"evt-1","sequence":1}
~~~

Target type Event or Mono<Event> produces one Event. If the body contains a large object, the decoder needs enough data to decode that object; memory limits apply to the data that must be buffered.

### Reading an Array into a Flux

With payload:

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2},
  {"id":"evt-3","sequence":3}
]
~~~

Target type Flux<Event> can emit sequentially:

~~~text
onNext(Event("evt-1", 1))
onNext(Event("evt-2", 2))
onNext(Event("evt-3", 3))
onComplete()
~~~

The decoder only emits an Event once the tokens for that Event are complete. If the third object has not arrived yet, the first two objects can already be delivered downstream. This is streaming at the decode layer; actual delivery speed also depends on the server, client, network, publisher, and demand.

### Reading NDJSON into a Flux

With:

~~~text
{"id":"evt-1","sequence":1}
{"id":"evt-2","sequence":2}
{"id":"evt-3","sequence":3}
~~~

Each line is a JSON value. The decoder uses the format's delimiter to identify each record. NDJSON is often more suitable when a producer wants to emit independent records over time rather than maintaining an unclosed JSON array.

### Note on Encoders: Flux + application/json Is Not Streaming by Default

There is an easy-to-overlook rule on the encoding side:

- With Mono<T>, the Jackson encoder serializes one value.
- With Flux<T> and media type application/json, by default the encoder collects elements via collectToList and serializes them into a JSON array.
- With streaming media types such as application/x-ndjson, the encoder writes and flushes each value in line-delimited format.

Therefore, **Flux<T> does not automatically mean the response is flushed item by item over the network**. If you want to stream individual records, choose an appropriate streaming media type and verify how the client consumes it.

## 9. Matching Content-Type and Accept to Data Structure

Two HTTP headers typically determine codec selection:

- **Content-Type:** the format of the body being sent.
- **Accept:** the response format the client wants to receive.

Examples:

| Body | Content-Type / Accept | Target or source type |
| --- | --- | --- |
| Single JSON object | application/json | Mono<Event> |
| JSON array, received as list | application/json | Mono<List<Event>> |
| JSON array, emitted per object | application/json | Flux<Event> |
| Multiple line-delimited JSON records | application/x-ndjson | Flux<Event> |
| Single text string | text/plain | Mono<String> |
| Multiple lines of text | text/plain or appropriate text format | Flux<String> |

Both JSON arrays and NDJSON can represent multiple objects, but their framing differs. A JSON array is one document with square brackets and commas; NDJSON is multiple JSON values separated by newlines.

If a client sends Accept application/json when an endpoint only produces application/x-ndjson, content negotiation may fail to find a matching representation. If Content-Type is unsupported by any reader, the server may return an unsupported media type error.

### JSON Array Response vs. NDJSON Response

Example handler returning Flux<Event>:

~~~java
@GetMapping(value = "/events/array", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Event> array() {
    return Flux.just(
        new Event("evt-1", 1),
        new Event("evt-2", 2));
}
~~~

The response is a JSON array. The default encoder collects elements and serializes them:

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2}
]
~~~

If you want to send individual records:

~~~java
@GetMapping(
    value = "/events/stream",
    produces = "application/x-ndjson")
public Flux<Event> stream() {
    return Flux.just(
        new Event("evt-1", 1),
        new Event("evt-2", 2));
}
~~~

The response consists of line-delimited JSON objects. The encoder can write and flush each element. For long-lived or infinite streams, design heartbeats/keep-alives if the protocol and client require early disconnect detection.

### WebClient Reading an Object, a List, and a Stream

~~~java
Mono<Event> one = webClient.get()
    .uri("/events/evt-1")
    .retrieve()
    .bodyToMono(Event.class);

Mono<List<Event>> batch = webClient.get()
    .uri("/events/array")
    .retrieve()
    .bodyToMono(new ParameterizedTypeReference<List<Event>>() {});

Flux<Event> stream = webClient.get()
    .uri("/events/stream")
    .accept(MediaType.valueOf("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Event.class);
~~~

Each call explicitly expresses the desired cardinality. Do not use bodyToMono(Event.class) for a multi-Event sequence; if a collection is needed, use ParameterizedTypeReference<List<Event>>; if processing each Event individually, use bodyToFlux(Event.class).

### WebClient Sending an Object or a Sequence

~~~java
Mono<Void> sendOne = webClient.post()
    .uri("/events/one")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new Event("evt-1", 1))
    .retrieve()
    .bodyToMono(Void.class);

Mono<Void> sendStream = webClient.post()
    .uri("/events/stream")
    .contentType(MediaType.valueOf("application/x-ndjson"))
    .body(Flux.just(
        new Event("evt-1", 1),
        new Event("evt-2", 2)), Event.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

bodyValue fits a single pre-existing object. body(Publisher, Class) fits a publisher of multiple objects. The media type must match the endpoint contract and configured encoder.

## 10. DataBuffer, Memory Limits, and Buffer Release

DataBuffer is Spring Core's byte buffer abstraction. It can wrap Java NIO ByteBuffer or a server buffer such as Netty ByteBuf. Some implementations use pooling and reference counting to reuse memory.

When an application uses @RequestBody, WebClient bodyToMono, or bodyToFlux with Java objects, default codecs are responsible for reading and managing DataBuffers. Normally you do not need to release buffers manually.

When reading raw bodies directly or writing a custom Decoder, you must manage buffer lifecycles carefully.

### Important Rules

1. **Buffers can be pooled:** release after reading if your code owns the buffer.
2. **Do not release buffers still managed by a codec:** ownership must be clear; releasing twice can cause errors.
3. **If retaining a buffer for later processing:** retain using the proper API and release symmetrically when done.
4. **If an operator drops items:** ensure discarded buffers are also released, typically via doOnDiscard(DataBuffer.class, DataBufferUtils::release).
5. **On error or cancel:** any held buffers must be freed.
6. **When aggregating multiple buffers:** prefer DataBufferUtils.join over ad-hoc byte array concatenation.

Illustrative ownership example in a custom decoder:

~~~java
Flux<DecodedValue> decoded = input
    .map(buffer -> {
        try {
            return decodeOneBuffer(buffer);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    })
    .doOnDiscard(
        DataBuffer.class,
        DataBufferUtils::release);
~~~

This example is only valid if decodeOneBuffer finishes reading the buffer immediately within the callback and keeps no reference to it. If the parser must retain bytes across multiple buffers, the custom decoder must properly design state, retain/release, and error/cancellation handling. Do not copy this illustrative snippet into an application as a general-purpose decoder.

### DataBufferUtils.join

DataBufferUtils.join can aggregate a Publisher<DataBuffer> into a single combined DataBuffer, potentially using a composite buffer to avoid copying when supported by the implementation. It is a convenient and safer utility when a complete buffer is genuinely needed.

Aggregating the entire body still consumes memory proportional to content size. If the body is large or a long stream, consider decoding element by element instead of joining the entire stream.

### maxInMemorySize

Decoders and HttpMessageReaders may buffer part or all of the input. WebFlux provides configuration to limit the number of bytes buffered in memory. When exceeded, reading may emit **DataBufferLimitException**.

This limit is useful in both cases:

- A large single object that must be fully buffered before decoding.
- A stream that must buffer one record until enough bytes arrive to split and decode that record.

For streaming decoders, the limit typically applies to the bytes of each individual object/record being split, not the total size of all elements across the entire stream.

Server-side configuration:

~~~java
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

WebClient configuration:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024))
    .build();
~~~

512 KiB in the example is a demo value, not a default recommendation for every system. Choose limits based on valid payload sizes, concurrency, available memory, and system protection requirements.

## 11. Backpressure and True Streaming

Flux allows downstream to request data by demand via Reactive Streams. The decoder can emit each object as soon as it is complete and downstream requests more data. This avoids building a List holding the entire sequence before processing begins.

However, three layers must be distinguished:

1. **Streaming decode:** the decoder emits individual objects instead of waiting to collect the entire list.
2. **Streaming encode:** the encoder writes each object to the response instead of collecting the entire Flux into a JSON array.
3. **Streaming transport:** server/client/network actually transmit and flush chunks over time.

An endpoint returning Flux<Event> that produces application/json may still collect all values into a List before writing the response. Conversely, NDJSON allows the encoder to write each record and flush per element.

If a stream can stay open for a long time, consider heartbeats or keep-alives to detect disconnected clients. If the client cannot consume fast enough, pipeline backpressure and buffering policies must be designed to avoid unbounded queues.

### When to Use Which Type?

| Need | Suitable type | Common format |
| --- | --- | --- |
| Fetch one resource | Mono<T> | application/json |
| Receive a batch and validate the whole batch | Mono<List<T>> | application/json array |
| Read an array and process elements individually | Flux<T> | application/json array |
| Receive continuous records over time | Flux<T> | application/x-ndjson |
| Push events to a browser | Flux<ServerSentEvent<T>> | text/event-stream |

## 12. Codec Configuration and Capabilities

WebFlux provides default codecs for byte[], ByteBuffer, DataBuffer, Resource, String, JSON, and other formats depending on dependencies. Jackson JSON is used when Jackson is present on the classpath.

Codecs can be customized via:

- **ServerCodecConfigurer:** codecs used for server requests/responses.
- **ClientCodecConfigurer:** codecs used for WebClient.
- **WebFluxConfigurer.configureHttpMessageCodecs:** customize default readers/writers or register codecs.
- **WebClient.Builder.codecs:** customize client-side codecs.

Not every decoder supports streaming decode. This capability depends on the parser and codec:

- Jackson has a non-blocking parser and supports decoding Flux for JSON arrays or line-delimited formats.
- Gson lacks an equivalent non-blocking parser; GsonDecoder does not support deserializing certain Flux streams and may throw UnsupportedOperationException.
- The Protobuf JSON decoder does not support reading streamed messages in the same way as the Protobuf binary delimited format.

Check the documentation of the actual codec configured. Simply declaring Flux<T> on a controller cannot add streaming capability that the decoder does not support.

### Special Note on Flux<String>

Jackson2JsonEncoder and Jackson2JsonDecoder by default do not treat String as a normal JSON object to serialize/deserialize. Spring typically handles String or String sequences as text/pre-serialized JSON content via CharSequenceEncoder.

If you want to return a JSON array of strings, consider collecting into a List and encoding Mono<List<String>>. If you want to stream lines of text, use an appropriate text media type. Never assume Flux<String> with application/json always creates a JSON array of strings.

## 13. Complete Java 17+ Example with Spring Boot WebFlux

The example below demonstrates how the same JSON array can be decoded into a single List or into multiple Events. It also includes an NDJSON endpoint to demonstrate sequence streaming.

### Project Structure

~~~text
webflux-codec-demo/
├── pom.xml
└── src
    ├── main/java/com/example/codec
    │   ├── CodecDemoApplication.java
    │   ├── Event.java
    │   └── CodecController.java
    └── test/java/com/example/codec
        └── CodecControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-codec-demo</artifactId>
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
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

Spring Boot 3.3.5 manages compatible versions of Spring Framework, Reactor, and Jackson. The example uses Java 17, Spring WebFlux, and JUnit 5.

### CodecDemoApplication.java

~~~java
package com.example.codec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}
~~~

### Event.java

~~~java
package com.example.codec;

public record Event(String id, int sequence) {
}
~~~

### CodecController.java

~~~java
package com.example.codec;

import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/codec")
public class CodecController {

    private static final MediaType NDJSON =
        MediaType.valueOf("application/x-ndjson");

    private static final List<Event> EVENTS = List.of(
        new Event("evt-1", 1),
        new Event("evt-2", 2)
    );

    @PostMapping(
        path = "/one",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Event> one(@RequestBody Mono<Event> body) {
        return body;
    }

    @PostMapping(
        path = "/array-as-list",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<Event>> arrayAsList(
            @RequestBody Mono<List<Event>> body) {
        return body;
    }

    @PostMapping(
        path = "/array-as-flux",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Event> arrayAsFlux(
            @RequestBody Flux<Event> body) {
        return body;
    }

    @PostMapping(
        path = "/ndjson",
        consumes = "application/x-ndjson",
        produces = "application/x-ndjson")
    public Flux<Event> ndjson(@RequestBody Flux<Event> body) {
        return body;
    }

    @GetMapping(
        path = "/array",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Event> array() {
        return Flux.fromIterable(EVENTS);
    }

    @GetMapping(
        path = "/stream",
        produces = "application/x-ndjson")
    public Flux<Event> stream() {
        return Flux.fromIterable(EVENTS);
    }
}
~~~

The endpoints demonstrate four processing patterns:

- POST /codec/one: one JSON object into Mono<Event>.
- POST /codec/array-as-list: one JSON array into Mono<List<Event>>.
- POST /codec/array-as-flux: the same JSON array decoded into Flux<Event>.
- POST /codec/ndjson: multiple line-delimited JSON records into Flux<Event>.
- GET /codec/array: Flux<Event> encoded as a JSON array.
- GET /codec/stream: Flux<Event> encoded as an NDJSON record stream.

### CodecControllerTests.java

~~~java
package com.example.codec;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@WebFluxTest(CodecController.class)
class CodecControllerTests {

    private static final MediaType NDJSON =
        MediaType.valueOf("application/x-ndjson");

    @Autowired
    private WebTestClient client;

    @Test
    void decodesOneJsonObjectAsMono() {
        client.post()
            .uri("/codec/one")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("id", "evt-1", "sequence", 1))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"id\":\"evt-1\",\"sequence\":1}");
    }

    @Test
    void decodesJsonArrayAsFluxElements() {
        client.post()
            .uri("/codec/array-as-flux")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(List.of(
                Map.of("id", "evt-1", "sequence", 1),
                Map.of("id", "evt-2", "sequence", 2)))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("[{\"id\":\"evt-1\",\"sequence\":1}," +
                  "{\"id\":\"evt-2\",\"sequence\":2}]");
    }

    @Test
    void decodesJsonArrayAsOneListValue() {
        client.post()
            .uri("/codec/array-as-list")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(List.of(
                Map.of("id", "evt-1", "sequence", 1),
                Map.of("id", "evt-2", "sequence", 2)))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("[{\"id\":\"evt-1\",\"sequence\":1}," +
                  "{\"id\":\"evt-2\",\"sequence\":2}]");
    }

    @Test
    void decodesNdjsonAsASequence() {
        Event first = new Event("evt-1", 1);
        Event second = new Event("evt-2", 2);

        FluxExchangeResult<Event> result = client.post()
            .uri("/codec/ndjson")
            .contentType(NDJSON)
            .body(Flux.just(first, second), Event.class)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(NDJSON)
            .returnResult(Event.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(first, second)
            .verifyComplete();
    }

    @Test
    void encodesFluxAsJsonArray() {
        client.get()
            .uri("/codec/array")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("[{\"id\":\"evt-1\",\"sequence\":1}," +
                  "{\"id\":\"evt-2\",\"sequence\":2}]");
    }

    @Test
    void encodesFluxAsNdjsonStream() {
        FluxExchangeResult<Event> result = client.get()
            .uri("/codec/stream")
            .accept(NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(NDJSON)
            .returnResult(Event.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new Event("evt-1", 1),
                new Event("evt-2", 2))
            .verifyComplete();
    }
}
~~~

Run tests:

~~~bash
mvn -q test
~~~

If all six tests pass, Maven exits with code 0. The two JSON array tests use the same payload with different controller signatures: one method receives a List, the other receives individual Events. The two NDJSON tests verify that the body publisher is encoded/decoded under the streaming media type.

Run the application:

~~~bash
mvn spring-boot:run
~~~

Send one object:

~~~bash
curl -i -X POST http://localhost:8080/codec/one -H "Content-Type: application/json" -d "{\"id\":\"evt-1\",\"sequence\":1}"
~~~

Send a JSON array:

~~~bash
curl -i -X POST http://localhost:8080/codec/array-as-flux -H "Content-Type: application/json" -d "[{\"id\":\"evt-1\",\"sequence\":1},{\"id\":\"evt-2\",\"sequence\":2}]"
~~~

Send NDJSON using Bash:

~~~bash
printf '%s\n' '{"id":"evt-1","sequence":1}' '{"id":"evt-2","sequence":2}' |
curl -i -X POST http://localhost:8080/codec/ndjson -H "Content-Type: application/x-ndjson" --data-binary @-
~~~

printf generates a real newline between the two records; --data-binary @- passes the exact stdin content to curl. Command escaping may differ in PowerShell, but the body must contain two JSON records on two lines.

## 14. Common Errors and Fixes

1. **Using Mono<T> for multiple objects:** Mono emits at most one value. Use Flux<T> or Mono<List<T>> depending on desired processing.
2. **Confusing Mono<List<T>> with Flux<T>:** both can accept the same JSON array, but one emits a single List while the other emits each T individually.
3. **Assuming JSON array and NDJSON are identical:** a JSON array is one document; NDJSON is multiple JSON values delimited by newlines.
4. **Assuming each DataBuffer is one object:** network chunks can split mid-object or hold multiple records. Rely on codecs/framing, not buffer boundaries.
5. **Using bodyToMono for a response stream:** the client only requests one value. Use bodyToFlux for sequences.
6. **Using bodyToFlux when the endpoint serializes only one object:** check actual data types and media types; Flux does not manufacture multiple elements by itself.
7. **Thinking Flux + application/json always flushes per element:** the default Jackson encoder collects Flux into a List to write a JSON array. Use NDJSON or SSE when streaming responses are needed.
8. **Sending adjacent JSON objects without a delimiter:** lacks explicit framing. Use a JSON array or NDJSON.
9. **Content-Type does not match consumes:** the reader may fail to match a codec or the request may be rejected.
10. **Accept does not match produces:** the server has no compatible representation and may return 406.
11. **Omitting ParameterizedTypeReference for List<T>:** Java type erasure loses the element type; the codec lacks generic type information.
12. **Assuming every codec supports Flux:** streaming capability depends on the decoder; verify the specific codec.
13. **Reading the body multiple times:** the request body is a stream; once consumed, it cannot be arbitrarily re-read from the raw body.
14. **Not bounding oversized objects:** a single large record can exceed maxInMemorySize and throw DataBufferLimitException.
15. **Raising maxInMemorySize indefinitely to avoid errors:** this lets a single request consume large amounts of memory; choose reasonable limits and stream large payloads.
16. **Manually joining DataBuffers and forgetting to release:** can cause memory leaks when the server uses pooled buffers.
17. **Releasing buffers owned by the framework:** can cause double-release or errors accessing freed buffers.
18. **Not handling cancellation in custom decoders:** the client closes the connection while retained buffers remain unreleased.
19. **Assuming NDJSON always ends with a trailing newline:** producers should terminate records with a newline by convention so parsers and line-based tools behave consistently.
20. **Using Flux<String> with Jackson as a JSON object sequence:** String has dedicated codec handling; use a DTO or an appropriate text media type.

## 15. Checklist for Choosing How to Decode

Before declaring request/response types, determine:

- **Cardinality:** one object, one List, or multiple independent objects?
- **Wire shape:** JSON object, JSON array, or NDJSON?
- **Target type:** Mono<T>, Mono<List<T>>, or Flux<T>?
- **Media type:** do Content-Type and Accept match the codec?
- **Codec:** does the current decoder support streaming for this type and media type?
- **Generic type:** is ParameterizedTypeReference needed for collections?
- **Memory:** does the largest single object/record fit within maxInMemorySize?
- **Backpressure:** does downstream consume by demand or build a large queue?
- **Response encoding:** Flux + application/json may be collected; is NDJSON/SSE needed?
- **Buffer ownership:** is your code reading DataBuffers directly or writing a custom codec?
- **Cancellation:** are buffers released on error or client disconnect?
- **Testing:** do tests distinguish object, List, Flux array, and NDJSON?

## 16. Self-Check Exercises

**Exercise 1.** The JSON body is a single object and the controller wants to receive one Event value. What is the appropriate type?  
**Answer:** Mono<Event> or Event depending on sync/reactive design; in reactive pipelines Mono<Event> is typically used.

**Exercise 2.** The JSON body is an array, but the service wants to receive the entire list as one unit. Which type should be used?  
**Answer:** Mono<List<Event>>.

**Exercise 3.** Same JSON array, but the service wants to process each Event individually. Which type should be used?  
**Answer:** Flux<Event>; the Jackson decoder can emit each array element once the object is complete.

**Exercise 4.** How does NDJSON differ from a JSON array?  
**Answer:** A JSON array is one JSON document with an array root; NDJSON is multiple independent JSON values delimited by newlines.

**Exercise 5.** Why can a single JSON object span multiple DataBuffers?  
**Answer:** A DataBuffer is a network byte chunk, not a message boundary. The network can split the body at any byte position.

**Exercise 6.** How do Decoder.decode and decodeToMono differ?  
**Answer:** decode creates a Flux<T> for multiple values; decodeToMono creates a Mono<T> for a single value.

**Exercise 7.** Does Flux<Event> returned with application/json flush each Event by default?  
**Answer:** No. The default Jackson encoder collects elements into a List and serializes them as a JSON array. Use a streaming media type such as application/x-ndjson when record-by-record flushing is needed.

**Exercise 8.** What does DataBufferLimitException indicate?  
**Answer:** The decoder/reader needed to buffer more bytes than the configured memory limit for the content being processed.

**Exercise 9.** Why shouldn't you manually release every DataBuffer in a controller?  
**Answer:** Codecs and the framework manage those buffers. Only code that directly owns a buffer must release it according to its lifecycle.

**Exercise 10.** Which WebClient APIs read one Event vs. multiple Events?  
**Answer:** bodyToMono(Event.class) for a single value; bodyToFlux(Event.class) for a sequence.

**Exercise 11.** If a decoder supports decodeToMono, does it necessarily support streaming Flux?  
**Answer:** No. Multi-value capability depends on the parser and the decoder's implementation.

**Exercise 12.** When should you choose Mono<List<T>> instead of Flux<T>?  
**Answer:** When business logic needs the whole batch as a single value, needs to inspect or process the entire list, and the batch size is bounded within memory limits.

## 17. Key Takeaways

**Mono<T>** represents at most one object; **Mono<List<T>>** represents a single value containing the whole list; **Flux<T>** represents multiple individual objects. The same JSON array can be decoded into a List or into a Flux of elements, depending on the target type and the decoder's capabilities.

A JSON array is one JSON document containing multiple elements. NDJSON is multiple JSON values separated by newlines, often better suited for streams of independent records. The Jackson decoder can emit each object of a JSON array or NDJSON into a Flux as soon as the object is complete. On the encoding side, Flux with application/json may be collected into a List by default; the application/x-ndjson media type allows writing and flushing each record individually.

DataBuffer is a byte chunk, not a message boundary. Codecs manage buffers when the application works at the object level; custom decoders or raw-body reading code must handle ownership, release, discard, cancellation, and memory limits. Choose cardinality, media type, codec, and maxInMemorySize according to actual data sizes and semantics.

### References

- Spring Framework, [Reactive Core – Codecs and Reactive HTTP Messages](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework, [Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- Spring Framework, [WebFlux HTTP Message Codec Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework, [WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Framework, [WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- Spring Framework Javadoc, [Decoder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/codec/Decoder.html).
- Spring Framework Javadoc, [DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html).
