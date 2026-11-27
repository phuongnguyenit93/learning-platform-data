# Handling String, byte[], and Binary Data

Messages in Spring Cloud Stream can carry text content, binary data, or a Java object converted from a payload. Choosing the right data type at the messaging boundary helps the application avoid character encoding errors, data corruption, unnecessary conversions, and differences across Kafka, RabbitMQ, or Pulsar binders.

Three common representations are **String**, **byte[]**, and binary objects in custom formats. String suits text content with a defined charset. byte[] suits cases where you need to preserve the raw octets received from the broker or send binary data. Formats such as images, PDFs, compressed files, Protobuf, or Avro require additional conventions around media type, schema, or metadata so the receiver can decode them properly.

## 1. Payload, Message, and Data Types

Spring Messaging represents a message with a payload and headers. The payload holds the main content; headers carry metadata such as content type, timestamp, correlation ID, or routing information.

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order has been confirmed")
        .setHeader(MessageHeaders.CONTENT_TYPE, "text/plain;charset=UTF-8")
        .build();
~~~

With Spring Cloud Stream, a function can receive the payload directly:

~~~java
@Bean
public Consumer<String> textConsumer() {
    return text -> processText(text);
}
~~~

Or receive the entire Message to inspect headers:

~~~java
@Bean
public Consumer<Message<byte[]>> binaryConsumer() {
    return message -> {
        byte[] payload = message.getPayload();
        Object contentType = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);
        processBinary(payload, contentType);
    };
}
~~~

Choose the parameter type based on the function's responsibility:

- Use **String** when the function needs decoded text content.
- Use **byte[]** when the function needs the raw bytes and should not convert them to a string.
- Use **Message<T>** when both payload and metadata in headers are needed.

Avoid converting every payload into a String just for logging or passing between functions. Decoding binary bytes as if they were text can lose data or introduce replacement characters.

## 2. Handling String and Charset

A String in Java is a sequence of Unicode characters. When transmitted over a broker, content must be encoded into bytes using a character encoding. UTF-8 is the common choice for distributed systems because it is widely supported and can represent all of Unicode.

When converting manually between String and byte[], always specify the charset:

~~~java
String text = "Hello Spring Cloud Stream";

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

Avoid overloads without a charset such as **getBytes()** or **new String(bytes)** at messaging boundaries. They rely on the runtime environment's default charset. Two instances running on different operating systems or JVM configurations may produce different results.

### Configuring bindings for text

Set the content type to text/plain and declare the charset if needed:

~~~yaml
spring:
  cloud:
    function:
      definition: textConsumer
      stream:
        bindings:
          textConsumer-in-0:
            destination: text-events
            group: text-reader
            content-type: text/plain;charset=UTF-8
~~~

In the configuration above, the application receives text payloads via the input binding. When the producer is also a Spring Cloud Stream application, set the matching content type on the output binding or on the outbound Message so the receiver has full conversion information.

Output binding example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        textPublisher-out-0:
          destination: text-events
          content-type: text/plain;charset=UTF-8
~~~

For text arriving from external systems, producers do not always send content type metadata. When metadata is missing, both sides must agree on the charset and format via an integration contract. Never rely on the host machine's default charset.

### Handling text encoding errors

If received bytes are invalid for the declared charset, constructing a String may replace malformed byte sequences with replacement characters. When data requires strict validation, use CharsetDecoder and configure error reporting behavior:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String text = decoder.decode(ByteBuffer.wrap(payload)).toString();
~~~

Decoding failures should be recorded as input data errors. Do not arbitrarily drop bytes or switch charsets to force continuation if doing so alters business meaning.

## 3. Handling byte[] as Raw Data

byte[] is a byte array in Java, suited for non-text payloads. A consumer receiving byte[] can store files, compute checksums, decode custom formats, or forward raw content to another service.

~~~java
@Bean
public Consumer<byte[]> imageConsumer() {
    return bytes -> {
        validateImage(bytes);
        imageStorage.store(bytes);
    };
}
~~~

Declare an appropriate content type, such as application/octet-stream for general binary data:

~~~yaml
spring:
  cloud:
    function:
      definition: imageConsumer
    stream:
      bindings:
        imageConsumer-in-0:
          destination: image-events
          group: image-storage
          content-type: application/octet-stream
~~~

If the format is known, use a more specific media type, such as **image/png**, **application/pdf**, or an organization-defined media type for custom payloads. The media type describes how to interpret data; it does not automatically verify that the bytes genuinely conform to that format.

### Sending byte[] via an output binding

A function can produce or forward byte[]:

~~~java
@Bean
public Function<byte[], byte[]> binaryTransform() {
    return input -> transformBinary(input);
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: binaryTransform
    stream:
      bindings:
        binaryTransform-in-0:
          destination: raw-input
          content-type: application/octet-stream
        binaryTransform-out-0:
          destination: raw-output
          content-type: application/octet-stream
~~~

If headers must be preserved, use a Function accepting and returning Message:

~~~java
@Bean
public Function<Message<byte[]>, Message<byte[]>> forwardBinary() {
    return message -> MessageBuilder.withPayload(message.getPayload())
            .copyHeaders(message.getHeaders())
            .build();
}
~~~

When copying headers, consider which headers actually make sense at the destination. Do not blindly forward internal binder headers, routing info, or metadata that is no longer valid after crossing another system boundary.

## 4. Content Type and Spring Cloud Stream's Conversion Mechanism

Spring Cloud Stream uses content type to select how to convert payloads between wire representation and the Java type expected by the function. Content type can be configured on the binding or carried with the Message as a header. When metadata comes from multiple sources, understand the precedence order and behavior of your Spring Cloud Stream version; do not assume a binding value always overrides a message header.

Some common media types:

| Content type | Meaning | Common Java type |
|---|---|---|
| **text/plain;charset=UTF-8** | UTF-8 text. | String |
| **application/json** | JSON data. | DTO, Map, or JsonNode depending on converter |
| **application/octet-stream** | Binary data with no specified format. | byte[] |
| **image/png** | PNG image. | byte[] or application-handled image type |
| **application/pdf** | PDF document. | byte[] |
| **application/x-protobuf** | Protocol Buffers payload under an agreed contract. | Schema-generated message class or byte[] |

Content type is metadata, not a data transformation. Setting **application/pdf** does not turn an arbitrary byte array into a PDF. The application still needs to verify format signatures, size, schema, or checksums when data requires safety and integrity.

### Example converting JSON and byte[]

Suppose a producer sends JSON as byte[]:

~~~java
byte[] json = """
        {"orderId":"ORD-1001","status":"CREATED"}
        """.getBytes(StandardCharsets.UTF_8);
~~~

If the consumer expects a DTO, the content type must indicate JSON and the converter must support converting to that type. If the consumer receives byte[], the application can control parsing directly:

~~~java
ObjectMapper mapper = new ObjectMapper();
OrderCreated event = mapper.readValue(json, OrderCreated.class);
~~~

The two approaches have trade-offs. Letting Spring Cloud Stream perform conversion allows functions to work directly with DTOs, reducing parsing code in business logic. Receiving byte[] is suitable when signature verification on raw bytes, verbatim storage, or a custom parser is needed. Avoid parsing the same payload multiple times across different layers.

## 5. Native Encoding and Native Decoding

Spring Cloud Stream can convert payloads using message converters before the binder sends or after the binder receives. Some binders also support native encoding/decoding, where the broker's serializer and deserializer handle data conversion.

With the Kafka binder, two commonly used binding-level options are:

- **producer.useNativeEncoding:** delegates serialization to the Kafka producer serializer.
- **consumer.useNativeDecoding:** delegates deserialization to the Kafka consumer deserializer.

Illustrative configuration example on an output and input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        binaryPublisher-out-0:
          destination: binary-events
          producer:
            use-native-encoding: true
        binaryReader-in-0:
          destination: binary-events
          group: binary-reader
          consumer:
            use-native-decoding: true
~~~

When using native encoding/decoding, the binder's serializer/deserializer must be configured to match the data type. If a consumer expects byte[] while the deserializer returns a different object, the function will not receive the expected payload type. Conversely, if the producer serializer expects a DTO while the application supplies byte[], ensure the serializer can handle that type.

Do not enable native encoding or decoding purely for speed without defining the wire format contract. When native conversion is used, Spring Cloud Stream's standard converters may not participate in that data path. Exact serializer/deserializer configuration depends on the binder and version; refer to the documentation for your Kafka, RabbitMQ, or Pulsar binder.

## 6. Structured Binary Formats

A binary payload often requires more information than a byte array alone. Systems must agree on:

1. **Format:** Protobuf, Avro, PDF, PNG, ZIP, or a custom format.
2. **Schema or version:** how fields are interpreted and compatibility rules.
3. **Encoding:** byte order, charset if text sections exist, framing rules, and length fields.
4. **Metadata:** schema ID, version, content type, correlation ID, or checksum.
5. **Limits:** maximum size, processing time, and storage policy.

For example, with a Protobuf payload, producers and consumers must share the same understanding of the schema or schema ID. A consumer cannot infer the full structure from byte[] alone without format information. With Avro, agree on the schema and how to retrieve it, such as via a schema registry if the architecture uses one.

A binary envelope can be designed to hold version and payload:

~~~java
public record BinaryEnvelope(
        String eventType,
        int schemaVersion,
        byte[] data,
        String checksum) {
}
~~~

This is only an in-memory model. When serializing the envelope, define an explicit wire format rather than sending a default Java representation and assuming other applications can read it. When evolving the schema, specify required fields, optional fields, default values, and how unsupported versions are handled.

### Do not confuse compression with encryption

Data compression reduces transmission or storage size; encryption protects confidentiality. These two purposes are distinct. A ZIP file or compressed payload remains readable without a separate encryption layer.

If using application-level compression, both sides must agree on the algorithm and how to identify compressed payloads. Metadata such as content-encoding can express this convention if the system and binder preserve the corresponding header. Never decompress untrusted payloads without bounding output size, because compressed data can expand dramatically.

## 7. Data Preservation and Payload Validation

With byte[], treat the data as an octet sequence that may contain any value from 0 to 255. Do not apply whitespace trimming, case folding, or Unicode normalization to binary bytes. Those operations are only meaningful for text decoded with the proper charset.

Useful validation steps:

- Verify the payload is non-null and its length is within bounds.
- Verify content type or format against the contract.
- Check magic bytes or file signatures when appropriate.
- Verify checksums or digital signatures if integrity verification is needed.
- Bound parsing, decompression, and processing time.
- Do not trust client-supplied filenames or content types without verification.
- Do not log full binary payloads; use size, checksum, or identifiers for diagnostics.

Size check example:

~~~java
private static final int MAX_PAYLOAD_BYTES = 5 * 1024 * 1024;

static void validateBinary(byte[] payload) {
    if (payload == null || payload.length == 0) {
        throw new IllegalArgumentException("Empty payload");
    }
    if (payload.length > MAX_PAYLOAD_BYTES) {
        throw new IllegalArgumentException("Payload exceeds limit");
    }
}
~~~

Limits should be chosen based on broker capacity, producer/consumer settings, JVM memory, and processing time. Even a payload smaller than the broker limit can cause memory pressure if many consumers process concurrently or the application retains multiple copies on the heap.

## 8. Sending and Receiving Binary Data via StreamBridge

StreamBridge allows business components to send payloads through an output binding. For binary data, you can send byte[] and set content type explicitly:

~~~java
public boolean publishDocument(StreamBridge bridge, byte[] document) {
    Message<byte[]> message = MessageBuilder
            .withPayload(document)
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/pdf")
            .build();
    return bridge.send("documentsOut", message);
}
~~~

Output binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: documentsOut
      bindings:
        documentsOut:
          destination: documents
          content-type: application/pdf
~~~

On the receiving side, the consumer can work directly with byte[]:

~~~java
@Bean
public Consumer<byte[]> documentConsumer(DocumentStore store) {
    return bytes -> {
        validatePdf(bytes);
        store.save(bytes);
    };
}
~~~

If the consumer needs the content type to select a parser, accept **Message<byte[]>** instead of bare byte[] to read metadata. Even so, headers may be altered or may not traverse every broker in the same way. For metadata critical to the data contract, consider placing it in an envelope or a controlled format field rather than relying solely on optional headers.

## 9. Testing String, byte[], and Binary Data

Conversion tests should verify both content and metadata. Checking only that the consumer was invoked is insufficient; prove that the payload retains its exact values after passing through the converter.

| Case | Test data | What to verify |
|---|---|---|
| UTF-8 String | Vietnamese text with diacritics, non-ASCII characters, and emojis. | Received string matches sent string with no charset corruption. |
| Arbitrary byte[] | Array containing byte 0, Java negative byte values, and boundary values. | Bytes are preserved at every position. |
| application/octet-stream | Non-text binary payload. | Consumer receives raw byte[] intact. |
| JSON to DTO | Schema-valid JSON and JSON missing optional fields. | Converter or parser constructs the object per contract. |
| Malformed JSON | Truncated payload or syntax errors. | Conversion error is handled according to retry/DLQ policy. |
| Mismatched content type | PDF bytes declared as text/plain. | Test catches contract mismatch instead of silently treating it as text. |
| Native decoding | Test binder serializer/deserializer. | Java type and wire format are compatible at both ends. |
| Oversized payload | Data exceeding application limit. | Rejected before causing memory pressure or disrupting the consumer. |

Byte-preservation check example:

~~~java
byte[] original = new byte[] {0, 1, 10, 13, 127, (byte) 0x80, (byte) 0xFF};
byte[] restored = Arrays.copyOf(original, original.length);

assertArrayEquals(original, restored);
~~~

In integration tests, send data through the test binder or a test broker and compare the received byte[] against the original data. When using Kafka, RabbitMQ, or Pulsar with native serialization, separately test the actual serializer/deserializer and corresponding broker configuration.

## 10. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Vietnamese/accented characters corrupted | Producer and consumer use different charsets or rely on default charset. | Standardize on UTF-8 and declare charset explicitly. |
| PDF or image corrupted | Binary payload converted to String or altered as text. | Use byte[] and an appropriate media type. |
| Consumer reports wrong payload type | Content type, function signature, or native deserializer mismatch. | Check Java types, converters, and serializer/deserializer on both sides. |
| DTO not converted | Content type is not JSON, converter missing, or schema incompatible. | Verify content type and conversion configuration. |
| Wrong content type header | Producer omitted metadata or binder did not preserve header as expected. | Set content type on binding and verify actual metadata; place critical metadata in an envelope if needed. |
| Large payloads increase memory usage | Multiple byte[] copies or concurrency exceeding heap capacity. | Enforce size limits, tune concurrency, and consider storing files outside the broker. |
| Native decoding returns unexpected type | Deserializer does not match function type or wire format. | Configure matching serializer/deserializer and test the contract. |
| Logs hard to diagnose for binary data | Logging raw payloads directly or logging a misdecoded string. | Log event ID, content type, size, and checksum. |

When investigating, first determine whether wire data is text or binary. Next, inspect charset or media type, function parameter type, active converters, and native encoding/decoding settings. Finally, verify the binder's serializer/deserializer and the actual payload on the broker.

## 11. Pre-Deployment Checklist

- [ ] Each binding has a content type matching its payload.
- [ ] Text uses an agreed charset, preferably UTF-8.
- [ ] Conversions between String and byte[] always specify charset explicitly.
- [ ] Binary payloads remain as byte[] or an appropriate binary type.
- [ ] Binary data is never decoded as text.
- [ ] Schema, version, and media type are agreed upon between producer and consumer.
- [ ] Native encoding/decoding is enabled only when serializer and deserializer are compatibly configured.
- [ ] Size, checksum, format, and processing time are validated as required.
- [ ] Logs do not record sensitive content or full payloads.
- [ ] Integration tests confirm payload and metadata preservation through a real binder.

In Spring Cloud Stream, String, byte[], and binary data are payload representations serving distinct purposes. String requires an agreed charset; byte[] preserves raw octets; structured binary formats require schemas and metadata for decoding. When content types, converters, and serializers/deserializers are configured consistently, applications can reliably exchange text, files, and binary data over Kafka, RabbitMQ, or Pulsar.
