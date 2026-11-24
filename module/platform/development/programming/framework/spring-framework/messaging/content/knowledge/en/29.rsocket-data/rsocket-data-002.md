# Codecs for Strings, Binary Data, and JSON Objects

## 1. What do codecs do in RSocket?

RSocket transmits payloads as binary data. At the application layer, clients and servers typically work with Java types such as `String`, `byte[]`, `ByteBuffer`, or DTOs. A **codec** is the component that converts between Java objects and the byte data portion of an RSocket payload:

- `Encoder` converts a Java value into bytes for sending.
- `Decoder` reads received bytes and recreates the Java value.
- MIME type describes the format of the data so both sides choose the appropriate encoding and decoding mechanism.

For example, the same content can be represented in several ways. The string `"hello"` can be raw UTF-8 bytes in `text/plain` or a quoted JSON string in `application/json`. A `User` object can be serialized as JSON. An image file can be transmitted as raw bytes without converting it to JSON.

RSocket does not inherently understand the structure of Java DTOs. Both sides must agree on the MIME type and have compatible encoders/decoders. If the client sends JSON while the server decodes it as binary data or plain text, the result will not match the application contract.

## 2. MIME types and RSocketStrategies

An RSocket connection declares a data MIME type and a metadata MIME type during `SETUP`. The data MIME type specifies how to interpret the data portion of payloads on the connection. Common examples:

| MIME type | Meaning | Common data |
|---|---|---|
| text/plain | Plain text | String |
| application/octet-stream | Binary bytes | byte[], ByteBuffer |
| application/json | JSON | DTO, record, Map, List |

In Spring, **RSocketStrategies** brings together components for payload handling, including encoders, decoders, metadata extractors, and route matchers. When sending an object via `RSocketRequester`, Spring selects an encoder matching the Java type and MIME type. When receiving a response or handling a payload on the server, Spring locates the corresponding decoder.

Spring includes foundational codecs for common simple and binary types such as `String`, `byte[]`, `ByteBuffer`, and `DataBuffer`. To convert DTOs into JSON, a JSON codec—typically Jackson—must be registered.

A strategy configuration with JSON support:

~~~java
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;

RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
    .build();
~~~

`Jackson2JsonEncoder` and `Jackson2JsonDecoder` belong to Spring Web and use Jackson 2. The application needs the corresponding Jackson dependencies on the classpath. With Spring Boot, ensure the required dependencies are included in the application; if an auto-configured or custom `RSocketStrategies` configuration already exists, inspect the actual codec list before adding duplicate codecs.

On the client, you can attach the strategies to `RSocketRequester.Builder` and declare the data MIME type:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/json"))
    .tcp("localhost", 7000);
~~~

On the server, register `RSocketStrategies` for `RSocketMessageHandler` to use. In a Spring configuration, you can declare a bean:

~~~java
@Bean
RSocketStrategies rSocketStrategies() {
    return RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();
}
~~~

If creating `RSocketMessageHandler` manually instead of using auto-configuration, attach `RSocketStrategies` to the handler according to the application configuration. Both client and server must have codecs matching the format used by the connection.

## 3. Sending strings with text/plain

For plain text data, the typical Java type is `String`. The string codec converts content to bytes using a charset, usually UTF-8, and the decoder converts received bytes back into a `String`.

Client:

~~~java
RSocketRequester textRequester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.parseMimeType("text/plain"))
    .tcp("localhost", 7000);

Mono<String> reply = textRequester
    .route("text.echo")
    .data("Hello RSocket")
    .retrieveMono(String.class);
~~~

Server:

~~~java
@Controller
class TextController {

    @MessageMapping("text.echo")
    Mono<String> echo(@Payload String message) {
        return Mono.just(message);
    }
}
~~~

The example above assumes the server has configured `RSocketMessageHandler` and the foundational codecs for strings. The client sends a `String`, Spring encodes it as request data; the server decodes it to `String`, processes it, and encodes the returned `String`.

**text/plain** represents plain text. The content `"hello"` is transmitted as text bytes, with no JSON structure. If the application needs to send a string while the connection is configured with `application/json` and the Jackson JSON codec, the string will be represented according to JSON rules, typically as a quoted JSON string. Therefore, both sides must agree on the MIME type and representation.

Do not manually convert `String` to `byte[]` and assume the decoder will automatically understand the content. If `byte[]` is chosen, the receiving type must also be `byte[]` or there must be an explicit character-decoding step with an agreed-upon charset.

## 4. Sending binary data with byte[] and ByteBuffer

For images, files, compressed content, or other binary data, `byte[]` or `ByteBuffer` can be used. These types preserve raw bytes without converting data into strings.

Example of a client sending and receiving `byte[]`:

~~~java
RSocketRequester binaryRequester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.parseMimeType("application/octet-stream"))
    .tcp("localhost", 7000);

byte[] imageBytes = loadImageBytes();

Mono<byte[]> stored = binaryRequester
    .route("files.store")
    .data(imageBytes)
    .retrieveMono(byte[].class);
~~~

Server side:

~~~java
@Controller
class FileController {

    @MessageMapping("files.store")
    Mono<byte[]> store(@Payload byte[] content) {
        // Validate and store content using the application's storage service.
        return Mono.just(content);
    }
}
~~~

This is an echo example to demonstrate the `byte[]` codec. In a real application, do not return the entire file by default if the business logic only needs to return a storage ID or processing status. Check file size, permissions, and file type before storing.

**application/octet-stream** represents general binary data. `ByteArrayEncoder`/`ByteArrayDecoder` can convert `byte[]` directly. When using `ByteBuffer`, data must be read according to the remaining region from `position` to `limit`; note that `position` may change as the buffer is read. When you need to preserve the original data for reuse, create an appropriate `duplicate` or `slice` instead of sharing a buffer that has already been consumed.

Spring also supports `DataBuffer` for low-level data handling scenarios. `DataBuffer` is suitable when integrating with Spring's reactive APIs, though when manipulating buffers directly, you must manage their lifecycle and release buffers properly if the buffer type requires releasing. For typical cases, `byte[]` or `ByteBuffer` is easier to understand and control.

## 5. Sending Java objects as JSON

DTOs are a convenient choice when requests or responses have multiple fields carrying business meaning. The JSON codec uses Jackson to serialize objects to JSON and decode JSON back into the corresponding objects.

DTO example:

~~~java
public record Greeting(String message, String sender) {}
~~~

Client sending a DTO and receiving a DTO:

~~~java
RSocketRequester jsonRequester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/json"))
    .tcp("localhost", 7000);

Mono<Greeting> reply = jsonRequester
    .route("greeting.echo")
    .data(new Greeting("Hello", "client-01"))
    .retrieveMono(Greeting.class);
~~~

Server handling:

~~~java
@Controller
class GreetingController {

    @MessageMapping("greeting.echo")
    Mono<Greeting> echo(@Payload Greeting greeting) {
        return Mono.just(greeting);
    }
}
~~~

When sending the request, `Jackson2JsonEncoder` converts `Greeting` to JSON. When the server receives the payload, `Jackson2JsonDecoder` recreates the `Greeting` object. The response direction also uses the JSON codec to convert the DTO back to the client.

The corresponding JSON example looks like:

~~~json
{
  "message": "Hello",
  "sender": "client-01"
}
~~~

The actual JSON structure depends on `ObjectMapper` configuration, naming strategy, annotations, and registered Jackson modules. Both sides must agree on field names, data types, date/time formats, enums, and how missing or null fields are handled. DTOs do not strictly need to be identical Java classes, but the exchanged JSON structure must be compatible.

Jackson supports records in modern versions. For regular classes, a constructor or object creation mechanism usable by Jackson is needed, along with getters/setters or appropriate configuration. If a DTO contains special types like `LocalDateTime`, `UUID`, or third-party library types, register the required Jackson modules and verify the actual serialized format.

## 6. Distinguishing JSON strings from plain text

A common mistake is assuming `String` is always transmitted the same way regardless of the MIME type.

With `text/plain`, the string:

~~~text
hello
~~~

is transmitted as plain text. With `application/json`, a `String` encoded according to JSON syntax looks like:

~~~json
"hello"
~~~

The quotation marks are part of the JSON representation. If the server receives JSON but reads it as plain text, the content may include the quotation marks or not be handled as expected.

Similarly, `byte[]` in `application/octet-stream` is raw bytes. If `byte[]` is serialized to JSON by Jackson, it can be represented as a Base64 string. The two representations serve different purposes:

- Use `application/octet-stream` and the `byte[]` codec when raw bytes must be transmitted as-is.
- Use `application/json` when you want to represent data according to JSON structure.
- Use `text/plain` when the content is strictly plain text.

Do not select a MIME type solely based on the Java type. Consider the wire format agreed upon by the client and server.

## 7. Single connection and MIME type selection

The data MIME type is declared in the RSocket connection's `SETUP`. Therefore, do not assume that merely changing the route can automatically switch the data format from `text/plain` to `application/json` or `application/octet-stream`.

If an application needs payload groups with different formats, design a clear connection contract. Common options:

1. Use one unified format, such as JSON, for DTOs and business requests on a single connection.
2. Use separate connections with appropriate data MIME types for text, binary, or JSON streams.
3. If a payload must carry multiple content types, design an envelope or metadata under an explicit contract and configure the corresponding decoding mechanism; do not guess the format solely from the route.

The metadata MIME type is configured separately from the data MIME type. Route metadata is also not the data payload. For instance, `setupRoute` or `requester.route` determines the target handler, whereas the codec and data MIME type determine how the data portion is converted.

## 8. Using JSON with lists and generic types

The JSON codec can convert collections and nested DTOs. Example of a server returning a list of `User`:

~~~java
record User(Long id, String name) {}

@MessageMapping("users.all")
Mono<List<User>> allUsers() {
    return userService.findAll().collectList();
}
~~~

The client can receive it using a generic type reference:

~~~java
Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(
        new ParameterizedTypeReference<List<User>>() {}
    );
~~~

`ParameterizedTypeReference` retains generic type information at runtime so Spring knows the target structure to decode into. If only `List.class` is passed, the `User` element type information is not fully preserved. The JSON codec is still responsible for converting JSON to objects; `ParameterizedTypeReference` only describes the target type.

When the response is a simple object, use `retrieveMono(User.class)`. For collections or nested types, use the corresponding `ParameterizedTypeReference`. The client-side Java type must match the JSON structure actually returned by the server.

## 9. Transferring large data and binary streams

Do not always read an entire large file into `byte[]` and send it in a single request. Doing so increases memory usage and can put pressure on the heap when multiple clients upload simultaneously.

For large data, consider splitting it into chunks and using RSocket's streaming or channel models. Reactive Streams provide backpressure so the receiver controls the rate of data consumption. Explicitly define:

- Chunk size and total size limits.
- Chunk ordering, transfer session ID, and detection of missing/duplicate chunks.
- Completion acknowledgment, retry, and transfer cancellation.
- Frame limits, timeouts, and temporary storage resources.
- Buffer release and mid-stream error handling.

RSocket can fragment payloads according to transport/protocol limits, but this does not replace a streaming design for very large files. Frame fragmentation does not mean the application already has chunk-based file management, resume capability, or storage acknowledgment.

## 10. Common codec errors and fixes

- **UnsupportedMediaTypeException or no encoder found:** check the MIME type, Java type, and list of encoders registered in `RSocketStrategies`.
- **Cannot decode JSON:** check the input JSON, Jackson dependencies, decoder, and `ObjectMapper` configuration.
- **Client receives Map instead of DTO:** check the target type passed to `retrieveMono`/`retrieveFlux`; for generics, use `ParameterizedTypeReference`.
- **String has unintended quotation marks:** check whether the connection uses `text/plain` or `application/json` and which encoder is selected.
- **byte[] turned into Base64:** check whether the data is being encoded as JSON or binary bytes. Use `application/octet-stream` for raw bytes.
- **Vietnamese text is corrupted:** align the charset and MIME type; `text/plain` typically uses UTF-8. For JSON, check the encoding and Jackson configuration.
- **DTO has null or missing fields:** compare the actual JSON, constructor, getters/setters, record components, and Jackson configuration.
- **One side uses JSON, the other uses octet-stream:** align the connection's data MIME type and configure matching codecs on both sides.
- **Error only occurs with large files:** check payload size, frame limits, timeouts, backpressure, and whether the entire file is being held in memory.

When debugging, inspect the actual payload in bytes or JSON with sensitive information masked, the connection's MIME type, the selected codec, and the Java type at the send/receive point. Never log secrets, tokens, personal data, or entire files just to troubleshoot codec errors.

## 11. Quick codec selection table

| Purpose | Java type | Data MIME type | Suitable codec |
|---|---|---|---|
| Send plain text | String | text/plain | CharSequenceEncoder / StringDecoder |
| Send raw bytes | byte[] | application/octet-stream | ByteArrayEncoder / ByteArrayDecoder |
| Use NIO buffer | ByteBuffer | application/octet-stream | ByteBufferEncoder / ByteBufferDecoder |
| Exchange DTOs | DTO / record | application/json | Jackson2JsonEncoder / Jackson2JsonDecoder |
| Exchange generic collections | List<T>, nested DTOs | application/json | Jackson JSON codec + ParameterizedTypeReference on receive |

The codec names are commonly used components in Spring's codec system; actual selection depends on MIME type, registration order, and data type. If the application has custom codecs, verify their `canEncode`/`canDecode` behavior.

## 12. Key takeaways

Codecs serve as the bridge between Java types and RSocket payload bytes. Use `text/plain` for plain text, `application/octet-stream` for binary bytes, and `application/json` for DTOs/records serialized by Jackson. `RSocketStrategies` manages encoders, decoders, and related processing components; `RSocketRequester` uses those strategies when sending and receiving data.

Client and server must agree on the data MIME type, data structure, and compatible codecs. When errors occur, inspect the actual wire format, MIME type, encoder/decoder, and target type. For large payloads, design with streaming and backpressure rather than loading all data into memory by default.
