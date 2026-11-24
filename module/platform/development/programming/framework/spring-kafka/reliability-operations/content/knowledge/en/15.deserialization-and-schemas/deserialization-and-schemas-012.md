# Pre-Deserialization Data Validation

In a Kafka system, a consumer can receive records containing invalid bytes: truncated payloads, formats mismatched with the producer's serializer, wrong schema IDs, abnormally large payloads, or headers whose declared format does not match the payload. Feeding those bytes straight into a JSON/Avro/Protobuf deserializer and handling errors only inside the listener can cause exceptions before the `@KafkaListener` method is invoked. Retrying the exact same failing payload will not repair the data and can hold the consumer at one offset, growing consumer lag.

**Pre-deserialization data validation** (or wire-level preflight) checks properties determinable from **bytes and Kafka headers** before converting bytes into domain objects. The goal is not validating all business rules; the goal is detecting records that violate format contracts early, bounding resource usage, and establishing an explicit error-handling path.

This lesson covers where to place checks, differences between pre- and post-deserialization validation, using `ByteArrayDeserializer` and custom `Deserializer`s, integrating `ErrorHandlingDeserializer`, routing to a dead-letter topic (DLT), safely storing raw payloads, and operational runbooks.

## 1. Where does deserialization happen in the pipeline?

Kafka stores keys and values as byte arrays. When the consumer calls `poll()`, the Kafka client uses `key.deserializer` and `value.deserializer` to convert bytes into Java types. The Spring Kafka listener container then receives `ConsumerRecord<K, V>`, applies container components, converts messages if needed, and only then invokes the listener.

~~~text
Kafka broker
    |
    | key, value + headers bytes
    v
KafkaConsumer.poll()
    |
    +--> key deserializer
    |
    +--> value deserializer
              |
              v
       ConsumerRecord<K,V>
              |
              v
       Spring Kafka container
              |
       message conversion / adapter
              |
              v
          @KafkaListener
              |
              v
       Business validation
              |
              v
       Side effects + ack/commit
~~~

If `JsonDeserializer` or an Avro deserializer throws an exception inside `poll()`, the listener has usually not been called yet. A `try/catch` inside `@KafkaListener` will not catch that error.

This dictates which layer should host each check:

| Location | Raw bytes available? | Domain object available? | Example check |
|---|---|---|---|
| Producer before publish | Possibly | Yes | Block non-conforming events before sending |
| Inside custom Kafka `Deserializer` | Yes | Not yet | Check size, framing, headers, magic byte, schema ID |
| Listener receiving `byte[]` via `ByteArrayDeserializer` | Yes | Not yet, if app decodes manually | Inspect bytes then call parser in listener/service |
| After Kafka deserializer, before business handler | Depends on pipeline | Yes | Bean Validation, enum, required fields, object schema |
| Inside business service | Not necessarily | Yes | Order state, policies, idempotency |

**Standard record interceptors, record filters, and `@KafkaListener` are not "pre-Kafka-deserialization" points** if the value deserializer already converted bytes into objects. To inspect raw bytes beforehand, pick a suitable deserializer or design your own decoding layer.

## 2. Why validate before deserializing?

### 2.1. Detecting wrong formats before the parser

A topic expected to receive JSON objects may instead contain Avro binary, plain text, or a JSON array. Format differences can be caught at wire framing or basic structural markers before Jackson attempts to construct objects.

However, checking "first byte is `{`" is not a complete JSON validator. Valid payloads may have leading whitespace, a BOM in some protocols, or different formats. Preflight checks must follow the topic's real contract, not arbitrary heuristics.

### 2.2. Bounding resources

An abnormally large record can cause:

- Heap pressure from allocating giant strings or object graphs.
- High CPU usage from parsing deeply nested JSON or huge element counts.
- High latency affecting `max.poll.interval.ms`.
- Pressure on databases and downstream services if the object triggers fan-out operations.

Checking `data.length` before instantiating objects is a simple way to reject payloads exceeding the application's budget. Still, it does not replace broker/producer message size limits, fetch configurations, or JSON parser depth limits.

### 2.3. Classifying errors to avoid pointless retries

Payloads with wrong schemas, magic bytes, or checksums cannot self-heal by retrying the same bytes. Network errors calling Schema Registry, on the other hand, may be transient. Separate **permanent data errors** from **temporary infrastructure errors** to prevent retry storms and avoid skipping records that could succeed once the dependency recovers.

### 2.4. Preserving evidence for recovery

When a deserializer cannot construct a domain object, recovery needs a way to store **raw bytes, keys, headers, and source topic/partition/offset**. If the app merely logs an exception string and commits past the record, the failing payload loses any practical investigative trail.

## 3. What can be checked from raw bytes?

Preflight checks are generally cheap, time-bounded, and avoid full object parsing:

| Category | Example | Notes |
|---|---|---|
| Null/tombstone | Value is `null` | May be valid on compacted topics; do not treat as error automatically |
| Size | Empty, exceeds app limit | Check before allocating objects |
| Framing | Magic byte, version byte, length prefix | Must match the actual protocol |
| Header contract | Content type, event type, encoding, schema version | Headers can be missing or wrong; never trust blindly |
| Encoding | Valid UTF-8, byte order, compression | Validate only per agreed content type |
| Integrity | Payload envelope CRC/checksum/signature if present | Kafka CRC does not replace application-level checksums |
| Schema metadata | Schema ID, subject/version for registry-backed formats | Validate structural ID validity before lookup |
| Resource budget | Max byte count, parser depth limits | Some limits apply only during parsing |

### 3.1. What cannot be known before deserialization

You cannot confirm whether business fields like `orderId` exist, amounts are positive, or enums are valid merely by peeking at the first few bytes. Full checks require parsing/schema validation or at least structural decoding. Pre-deserialization validation is the **first line of defense**, not a replacement for post-decode validation.

A reliable system usually layers checks:

~~~text
Raw bytes
  |
  +-- Preflight: size, framing, metadata, integrity
  |
  +-- Deserialize: build object or parse tree
  |
  +-- Schema validation: types, required fields, compatibility
  |
  +-- Business validation: state, quotas, domain rules
  |
  +-- Persistence/idempotency
~~~

## 4. Two common implementation strategies

### Strategy A: Read byte[] and deserialize explicitly

Configure the Kafka consumer to use `ByteArrayDeserializer` for values; the listener receives `byte[]` and validates before calling the JSON/Avro parser. This approach is easy to understand, easy to instrument, and makes the preflight boundary obvious.

Pros:

- The listener definitely sees raw bytes before the application parser runs.
- Record headers can be inspected alongside the payload.
- Parser exceptions surface along the listener path, so listener error handling can classify them.
- Easy to record source metadata, route to DLT, and preserve evidence.

Trade-offs:

- The listener/service takes responsibility for decoding and validating properly.
- Avoid unnecessarily parsing the same payload multiple times.
- You cannot rely on the container auto-constructing domain objects during Kafka deserialization.

### Strategy B: Custom Kafka Deserializer wrapping preflight checks

Write a `Deserializer<T>` that checks raw bytes before calling a decoder/delegate. This keeps the listener API receiving typed domain objects, though exceptions can arise **inside `KafkaConsumer.poll()`**. Therefore, integrate `ErrorHandlingDeserializer` and proper recovery so deserialization failures do not stall the consumer without DLT routing.

Pros:

- Centralizes wire-level rules in one place.
- Consumers continue receiving typed objects.
- Fits checking magic bytes, framing, and metadata for a standard format.

Trade-offs:

- Must manage deserializer lifecycle, thread safety, and delegate configuration.
- Error handling at the deserialization layer is more complex.
- Undecodable payloads must still be preserved for recovery.

**Choose one primary strategy per consumer path** to avoid duplicate decoding and prevent different layers from enforcing conflicting error policies.

## 5. Example: ByteArrayDeserializer and checks before the JSON parser

Suppose topic `orders.events` has a contract: values are UTF-8 JSON objects, max 256 KiB; empty records are invalid, while tombstones must follow topic policy.

### 5.1. Spring Boot configuration

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-consumer
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.ByteArrayDeserializer
    listener:
      ack-mode: record
~~~

With this configuration, the consumer does not use `JsonDeserializer` at the Kafka client layer for values. The listener receives raw bytes.

### 5.2. A small preflight validator

~~~java
public final class OrderWirePreflight {
    private static final int MAX_BYTES = 256 * 1024;

    private OrderWirePreflight() {}

    public static void check(byte[] bytes) {
        if (bytes == null) {
            throw new InvalidWireRecordException(
                    "Tombstone is not allowed on orders.events");
        }
        if (bytes.length == 0) {
            throw new InvalidWireRecordException("Empty payload");
        }
        if (bytes.length > MAX_BYTES) {
            throw new InvalidWireRecordException(
                    "Payload exceeds configured size limit");
        }

        int pos = 0;
        while (pos < bytes.length && isJsonWhitespace(bytes[pos])) {
            pos++;
        }
        if (pos == bytes.length || bytes[pos] != (byte) '{') {
            throw new InvalidWireRecordException(
                    "Expected a JSON object envelope");
        }
    }

    private static boolean isJsonWhitespace(byte b) {
        return b == ' ' || b == '\t'
                || b == '\r' || b == '\n';
    }
}
~~~

Dedicated exception for wire validation:

~~~java
public class InvalidWireRecordException extends RuntimeException {
    public InvalidWireRecordException(String message) {
        super(message);
    }
}
~~~

The check above **does not validate JSON structural correctness**. It only rejects empty/oversized records and records lacking a JSON object prefix per the example contract. If the system allows a UTF-8 BOM or other valid envelopes, define and strip/handle them before enforcing the leading-character rule.

### 5.3. Listener checks before deserializing

~~~java
@Component
public class OrderRawListener {
    private final ObjectMapper objectMapper;
    private final OrderService orderService;

    public OrderRawListener(
            ObjectMapper objectMapper, OrderService orderService) {
        this.objectMapper = objectMapper;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "orders-consumer")
    public void listen(ConsumerRecord<String, byte[]> record)
            throws JsonProcessingException {

        byte[] raw = record.value();
        OrderWirePreflight.check(raw);

        // Business object is created only after wire-level preflight.
        OrderEvent event =
                objectMapper.readValue(raw, OrderEvent.class);

        // Schema/bean/business validation continues here.
        orderService.processIdempotently(event);
    }
}
~~~

If `OrderWirePreflight.check` or `objectMapper.readValue` throws an exception, the listener does not complete normally. The container error handler can classify the error, retry, or publish to DLT per policy. Never `catch` the exception, call `log.warn`, and return normally: doing so lets offsets advance past an unrecovered record.

### 5.4. Classifying data errors as non-retryable

Example `DefaultErrorHandler` with recoverer:

~~~java
@Bean
DefaultErrorHandler errorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L));

    handler.addNotRetryableExceptions(
            InvalidWireRecordException.class,
            JsonProcessingException.class);
    return handler;
}
~~~

Crucially, the DLT producer's serializer must support **`byte[]`** if the listener receives byte values. The example assumes `KafkaTemplate<Object, Object>` and serialization/recoverer are configured properly; otherwise, DLT publishing failures can break recovery. Real configurations should pick `ByteArraySerializer` or a type-appropriate serializer mechanism.

`JsonProcessingException` is a checked exception used by Jackson; the error handler receives an exception wrapped by the listener, so classification must be verified against the cause chain in your deployment version. If your policy requires distinguishing malformed JSON from infrastructure errors, catch `JsonProcessingException` at decode time and wrap it in a non-retryable custom exception while keeping the original cause.

## 6. Checking Kafka headers before the parser

Headers can describe the data format promised by the producer:

- `content-type`: e.g., `application/json`.
- `event-type`: e.g., `OrderCreated`.
- `schema-version`: schema or payload contract version.
- `encoding`: e.g., `utf-8`.
- `trace-id` or `correlation-id`: for tracing, not payload validity.

Example checking a required header:

~~~java
private static void requireJsonContentType(Headers headers) {
    Header header = headers.lastHeader("content-type");
    if (header == null || header.value() == null) {
        throw new InvalidWireRecordException(
                "Missing content-type header");
    }

    String contentType = new String(
            header.value(), StandardCharsets.US_ASCII);

    if (!"application/json".equalsIgnoreCase(contentType)) {
        throw new InvalidWireRecordException(
                "Unsupported content type");
    }
}
~~~

Call `requireJsonContentType(record.headers())` before `readValue` if the contract **mandates** this header. If legacy producers omit the header, plan a transition; enforcing a strict rule suddenly can send all older records to the DLT.

### 6.1. Do not trust headers blindly

Headers are sent by producers and may be altered by middleware. `content-type: application/json` does not prove the payload is valid JSON. Likewise, `schema-version: 3` does not guarantee contents actually conform to version 3.

Use headers to select the right codec and policy; parsers/schema validators must still validate the actual data. Across trust boundaries, treat headers as untrusted input until validated against the protocol.

### 6.2. Checking header count and size

A record can carry multiple duplicate-named headers or headers holding large byte payloads. If the application forwards headers into logs, maps, or downstream calls, bound them and keep only valid ones. Never call `toString()` on all headers in `INFO` logs because it can leak tokens, PII, or bloat logs.

## 7. Binary formats and magic bytes

With Avro/Protobuf or custom codecs, preflight typically checks envelope structure rather than JSON characters. For instance, the traditional **Confluent Schema Registry wire format** places a magic byte at index 0 and the schema ID in the next four bytes, followed by the payload.

~~~text
Byte index:   0      1  2  3  4       5...
             +------+-----------+---------------+
             |magic | schema ID | binary payload|
             +------+-----------+---------------+
               1 B       4 B       variable
~~~

This is an example of a **specific protocol**, not a standard for every Avro/Protobuf/Kafka serializer. Other serializers use different formats, additional message indexes, or custom prefixes. Only enforce preflight rules matching the producer's real serializer.

### 7.1. Checking framing

~~~java
public static int readSchemaId(byte[] bytes) {
    if (bytes == null || bytes.length < 5) {
        throw new InvalidWireRecordException(
                "Not enough bytes for registry framing");
    }
    if (bytes[0] != 0) {
        throw new InvalidWireRecordException(
                "Unexpected magic byte");
    }
    int schemaId = ByteBuffer.wrap(bytes, 1, 4).getInt();
    if (schemaId <= 0) {
        throw new InvalidWireRecordException(
                "Invalid schema id");
    }
    return schemaId;
}
~~~

The snippet assumes magic byte = 0 and positive schema IDs per the deployed contract. This check only reads framing; it **does not prove the schema ID exists in the registry or that the binary payload matches that schema**. For formats where empty payloads are valid, do not arbitrarily enforce `length > 5`.

### 7.2. Checking Schema Registry properly

After framing preflight, the codec may query Schema Registry for the schema by ID. Separate the cases:

| Scenario | Nature | Suggested policy |
|---|---|---|
| Wrong magic byte | Wrong payload format or wrong producer codec | Non-retryable, save raw bytes to recovery |
| Truncated envelope | Data violates contract | Non-retryable, investigate producer |
| Schema ID does not exist | Likely metadata/schema deployment bug | Alert and investigate; conditional retry if registry just changed |
| Registry timeout/503 | Temporary infrastructure unavailability | Bounded retry with backoff |
| Binary mismatches schema | Corrupted data/wrong serializer | Non-retryable if retrying same bytes cannot fix it |

Do not lump every exception mentioning "schema" into non-retryable: a schema-lookup timeout is completely different from a payload with an invalid schema ID. If the registry client has its own caching and retries, count total attempts to avoid retry storms.

## 8. Custom Deserializer validating data at the Kafka layer

When you want listeners to receive `OrderEvent` while still inspecting raw bytes before Jackson deserializes, use a custom `Deserializer<OrderEvent>`.

The example below includes the headerless overload too:

~~~java
public class ValidatingOrderDeserializer
        implements Deserializer<OrderEvent> {

    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public OrderEvent deserialize(String topic, byte[] data) {
        return deserialize(topic, new RecordHeaders(), data);
    }

    @Override
    public OrderEvent deserialize(
            String topic, Headers headers, byte[] data) {
        if (data == null) {
            // Tombstone policy: illustrative example allowing null.
            return null;
        }

        try {
            OrderWirePreflight.check(data);
            return mapper.readValue(data, OrderEvent.class);
        }
        catch (Exception ex) {
            throw new SerializationException(
                    "Cannot deserialize order event from " + topic,
                    ex);
        }
    }
}
~~~

This is a technical illustration. In production, the deserializer must manage configuration, release resources in `close()` if any, and never embed raw payloads or sensitive data in exception messages. If a codec is shared across threads, guarantee thread safety for shared objects.

In this example, exceptions thrown from the deserializer occur at the Kafka client polling layer. Using this deserializer directly without proper error handling can prevent the container from receiving a deserialized record or conveniently routing raw bytes to the DLT. That is why `ErrorHandlingDeserializer` is needed.

## 9. ErrorHandlingDeserializer and safe recovery paths

Spring Kafka's `ErrorHandlingDeserializer` wraps a delegate deserializer. When the delegate fails to deserialize a key/value, the wrapper records error details in the corresponding header, allowing the Spring Kafka container/error handler to handle it instead of letting Kafka `poll()` fail repeatedly at the same offset.

~~~text
Broker raw bytes
      |
      v
ErrorHandlingDeserializer
      |
      v
ValidatingOrderDeserializer (delegate)
      |
      +--> Preflight succeeded --> parse --> OrderEvent
      |
      +--> Preflight/parse failed
                      |
                      v
             Deserialization error metadata
                      |
                      v
              Spring Kafka error handler
                      |
                      v
                Recovery / DLT
~~~

### 9.1. Consumer configuration

Spring Boot example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-consumer
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": com.example.kafka.ValidatingOrderDeserializer
    listener:
      ack-mode: record
~~~

`com.example.kafka.ValidatingOrderDeserializer` is illustrative; substitute your real class. `ErrorHandlingDeserializer` supports additional declarations for keys, delegates, and fallback options depending on the Spring Kafka version.

**Note:** if keys can also be malformed, design error handling for keys too. A key deserializer throwing exceptions directly can likewise prevent the consumer from reaching the listener.

### 9.2. Do not auto-ack records that failed deserialization

An undecodable record must not be marked "handled successfully" merely because the wrapper caught the exception. The container/error handler must decide to send it to DLT, conditionally retry, or stop for investigation.

Certain failures are **non-retryable** by default in `DefaultErrorHandler`, including deserialization/conversion failures. The list and cause-inspection logic vary by version; with custom `SerializationException`s or custom wrappers, declare classifications explicitly and test them.

### 9.3. Preserving raw payloads for DLT

When using `ErrorHandlingDeserializer`, Spring Kafka supports recovery for records with deserialization errors and can forward original bytes to the DLT. However, the DLT producer must have serializers supporting the data types emitted by the recoverer:

- Decodable records may carry domain objects.
- Undecodable records may require storing raw `byte[]`.
- Keys may also be raw bytes if the failure was on the key.

Do not force every DLT value through `JsonSerializer<OrderEvent>` when records failed during deserialization. Use type-compatible serializers, such as `DelegatingByTypeSerializer` or a dedicated `KafkaTemplate` for raw bytes, depending on version and design.

Real tests must confirm failed records actually publish to the DLT and can be read back as bytes, not merely assert that the error handler was invoked.

## 10. Kafka max message size does not replace preflight

Kafka enforces limits on message/record batch sizes like `message.max.bytes` or `max.message.bytes` at broker/topic level, along with producer request and consumer fetch settings. Those settings protect transport and brokers up to a point.

Application-level preflight has a different purpose: capping **the payloads and structures a business consumer accepts**. For example, a cluster permits large records for shared topics while the order-processing consumer permits at most 256 KiB.

Do not try to solve oversized records by lowering `max.poll.records`. That property caps how many records one poll returns, not the size of an individual record.

Do not rely on `fetch.max.bytes` as a hard per-record cap either: the Kafka client includes batch-fetch progress guarantees so consumers can still advance when a record batch exceeds configured fetch limits. Enforce application limits explicitly.

## 11. Checking UTF-8, JSON depth, and malicious payloads

Checking the first byte is only a lightweight check. A JSON payload can start cleanly with `{` yet contain:

- Invalid UTF-8.
- Deeply nested structures.
- Enormous strings or arrays.
- Objects with more fields than expected.
- Duplicate fields or schema-mismatched types.
- Dangerous strings if passed unchecked into SQL, URLs, or file paths.

### 11.1. UTF-8 must be validated when required by contract

If the producer promises UTF-8 JSON, Java can use a decoder configured with `CodingErrorAction.REPORT` to reject invalid byte sequences. Calling `new String(bytes, UTF_8)` may silently substitute replacement characters for invalid bytes; never treat constructing a `String` as proof of valid payload encoding.

Example:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String json = decoder.decode(
        ByteBuffer.wrap(raw)).toString();
~~~

This example requires handling `CharacterCodingException` and budgeting memory when allocating `String`. For large payloads, decoding the entire string solely to check encoding can be expensive; many JSON parsers already validate encoding while streaming bytes.

### 11.2. Parser depth limits

Byte length alone cannot prevent deeply nested payloads. When using Jackson or other libraries, configure parser limits such as maximum nesting depth, string length, number length, or token count per your version's API.

Do not set every limit sky-high just to "avoid errors". Choose limits grounded in business contracts, actual data, and producer trust levels.

### 11.3. Never use uncontrolled polymorphic deserialization

If using JSON carrying class type info in headers or payloads, never enable features allowing arbitrary class instantiation from untrusted data. Use trusted type/package allowlists, explicit mappings, and restrict accepted event types. Never treat a type header as trustworthy proof of a safe class.

## 12. Tombstones, empty payloads, and null semantics

In compacted topics, a tombstone is a record with a key and a `null` value. It can represent deleting state for that key. If preflight always errors when `data == null`, the consumer can break the compacted topic's contract.

Distinguish:

| Case | Possible meaning | Decision depends on |
|---|---|---|
| `data == null` | Tombstone or protocol-level null value | Topic contract, retention/compaction, state store |
| `data.length == 0` | Empty byte array | Payload contract, not identical to null |
| Bytes containing JSON `null` | JSON literal null | JSON contract and domain semantics |
| `{}` | Empty JSON object | Schema required fields |
| Unparseable arbitrary bytes | Malformed payload | Parser/schema validator |

A topic may permit tombstones while forbidding empty payloads. Handling must be documented in contracts and tests rather than applying one blanket rule across all consumers.

## 13. Schema evolution and version checks

Consumers frequently run alongside multiple producer versions during rolling deployments. Preflight must fit the schema evolution strategy.

Example:

- Producer v1 emits JSON with `schema-version: 1`.
- Producer v2 adds optional fields and emits `schema-version: 2`.
- New consumers support both v1 and v2.

If preflight only accepts v2 while the topic still contains v1 records, the application will route large volumes of valid prior data into the DLT. That is not a safe schema evolution rollout.

A clear version contract can specify:

1. Which versions the consumer accepts.
2. Rules to upcast old versions into the current model.
3. How unknown/new fields are handled.
4. Size and data type limits per version.
5. Upgrade plans for producers/consumers and replaying old records.

### 13.1. A schema ID does not equal a valid schema

Magic bytes and schema IDs may be structurally sound while the registry deleted the schema or the payload violates it. After preflight, the codec/schema validator must still verify actual data. Never pass a record to business logic merely because a header carries a positive schema ID.

### 13.2. Handling registry outages

If the error is a registry timeout, retrying is more sensible than immediate DLT in some systems. Still, use backoff, deadlines, and circuit breakers to avoid hundreds of consumers hammering an unhealthy registry simultaneously. Cached schemas can keep systems running; cache/TTL settings must follow compatibility and security needs.

## 14. Handling errors by category

A reference policy table:

| Error | Retry? | Recommended recovery |
|---|---|---|
| Payload exceeds app size limit | No, unless contract changes | DLT raw bytes or quarantine, alert producer |
| Wrong magic byte | Usually no | DLT; inspect producer serializer |
| Malformed JSON | Usually no | DLT; record parse error metadata |
| Schema ID does not exist | Depends on cause | Investigate registry/deploy; finite retry if transient |
| Schema Registry timeout | Bounded | Backoff/circuit breaker; alert if prolonged |
| Signature verification failed | Usually no | Quarantine, severity-appropriate security alert |
| Unsupported null tombstone | No | DLT/quarantine or update contract |
| Missing business field | Usually no | Schema/business validation error, DLT |
| Database timeout after deserialization | Yes, if idempotent | Listener retry, do not blame wire format |

Do not retry every `SerializationException` under one policy if it mixes data errors and network errors. With custom deserializers, keep exception types/causes intact so the error handler can classify them.

### 14.1. How does quarantine differ from DLT?

A **DLT** is a topic storing failed records for investigation/replay. **Quarantine** usually describes an isolated stream/store reserved for untrusted or contract-violating payloads with stricter access controls and security workflows.

There is no mandatory Kafka API named `quarantine`. Systems can use a DLT as quarantine provided ACLs, encryption, retention, and safeguards against auto-replaying dangerous payloads are enforced. Name and scope boundaries per real policy.

## 15. Preserving keys, headers, and source locations on error

An undeserializable record can still carry valuable metadata:

- Source topic, partition, offset.
- Kafka timestamp.
- Key or key bytes.
- Producer/event ID if present.
- Format, schema, and correlation ID headers.
- Exception class, message, and root cause.

DLT recoverers can copy this metadata into DLT headers. Keep source offsets distinct from DLT offsets: they belong to different logs.

When storing raw bytes in a database/object storage, log a stable reference alongside source metadata rather than dumping full payloads to console logs.

### 15.1. A failed record may be republished multiple times

If the DLT producer wrote the record successfully yet the consumer crashed before committing the source offset, the record can be redelivered and appear in the DLT again. Thus, audit/recovery needs an idempotency key, such as event ID or `(original topic + partition + offset)` plus consumer group per problem scope.

Never use the DLT offset as a unique key to conclude two records are the same event: republished copies have different DLT offsets.

## 16. Never commit offsets when recovery is unsafe

A crucial rule: **Never acknowledge an unprocessable record until it has been processed or persisted onto a durable recovery path per design.**

Risky example:

~~~text
Record at offset 90
     |
     v
Preflight detects malformed bytes
     |
     v
Application only logs WARN
     |
     v
Listener returns normally
     |
     v
Container commits offset 91
     |
     v
Failed record has no retry path left
~~~

Proper flow:

~~~text
Invalid record
     |
     v
Exception is classified
     |
     v
Recoverer sends to DLT/quarantine
     |
     +---- Publish succeeds -----> Handler completes
     |                              |
     |                              v
     |                     Commit per ack policy
     |
     +---- Publish fails --------> Do not mark as recovered;
                                    raise alert and retry per policy
~~~

Commit details depend on `AckMode`, transactions, error handlers, and Spring Kafka version. Never assume calling `kafkaTemplate.send()` completed publishing: with async producers, inspect publish results and exceptions.

## 17. Observability for pre-deserialization validation

A system may have few failing records yet suffer major impact if they sit at the head of a partition and block progress. Monitor both **data error rates** and **consumer impact**.

| Metric | Meaning |
|---|---|
| Preflight reject count/rate | Records rejected due to framing/header/size |
| Deserialization failure rate | Parser/codec failures |
| Failures by normalized reason | Categorized size, magic byte, schema, encoding, null |
| Schema Registry error rate | Lookup/timeout/5xx errors |
| DLT publish success/failure | Whether the recovery path works |
| Consumer lag by partition | Whether a partition is blocked by a bad record |
| Oldest unprocessed record age | Real latency vs. SLO |
| Processing duration | Cost of preflight + deserialize + business logic |
| Raw payload size histogram | Data size trends |

### 17.1. Structured logs

A log should include:

~~~text
service=orders-consumer
group=orders-consumer
topic=orders.events
partition=2
offset=1708
stage=pre_deserialize
reason=invalid_magic_byte
payloadBytes=412
schemaId=unknown
recovery=dlt_requested
~~~

This is illustrative data. Real logs must omit raw payloads, tokens, or sensitive fields unless explicitly authorized by policy. Logging payload hashes can support deduplication, while weighing leakage and collision risks for your use case.

### 17.2. Metric tags

Tags should have low cardinality such as `service`, `topic` (bounded set), normalized `reason`, and `environment`. Never use event ID, offset, order ID, exception message, or raw header values as tags because they explode time series counts.

### 17.3. Alerts

Configure alerts when:

- Deserialization failures spike abnormally after a producer deployment.
- A schema version goes unrecognized by consumers.
- DLT publishing fails.
- A partition sees rising lag while processing rate is zero.
- Schema Registry timeouts persist.
- Rate of payloads exceeding size limits climbs rapidly.
- Quarantine backlog or unprocessed record age exceeds SLA.

## 18. Runbook: consumer failing repeatedly at the same offset

1. Identify consumer group, topic, partition, and offset from logs.
2. Check whether the exception occurs in the Kafka deserializer, message converter, or inside the listener.
3. If the Kafka deserializer throws directly, check whether `ErrorHandlingDeserializer` is enabled.
4. Inspect payload bytes, framing, and header contracts with safe tools under data-access policies.
5. Separate transient registry/network failures from permanent data errors.
6. Check whether the error handler/recoverer is configured on the right factory.
7. Confirm the DLT serializer supports raw bytes of failing records.
8. Verify DLT publishing and committed offsets before/after recovery.
9. Fix the producer, serializer, or schema, then perform controlled replay.

Never run commands modifying group offsets to skip a record without approval under data-governance procedures. Skipping offsets can forfeit processing critical events.

## 19. Runbook: many records rejected after a deployment

1. Compare error onset timestamps against new producer/consumer versions.
2. Group rejections by cause: size, framing, schema, encoding, headers.
3. Identify which producer generated failing records; do not look solely at consumers.
4. Check schema compatibility and versions in the rollout.
5. Check whether preflight accidentally tightened contracts against older records.
6. Check whether valid data hit false positives due to whitespace/BOM/tombstones.
7. If rollback is needed, verify compatibility with new records already in the topic.
8. After fixing, replay DLT/quarantine in small batches and reconcile idempotency.

False positives in preflight can be severe: large volumes of valid records marked corrupted simply because a check was overly simplistic. Therefore, rules must stay tightly aligned with producer contracts and schema versions.

## 20. Runbook: failure publishing raw payloads to DLT

1. Check the actual runtime type of the value after `ErrorHandlingDeserializer`.
2. Check whether the DLT producer serializer supports `byte[]`.
3. Check whether the producer forces a domain-object serializer for all records.
4. Verify DLT topic existence, ACLs, partition routing, and message size limits.
5. Inspect async send results, timeouts, and broker errors.
6. Confirm the error handler does not mark recovery succeeded when DLT publishing errors.
7. Re-test with a controlled broken deserialization record.

Never "fix" DLT failures by swallowing exceptions or committing past the source record. That turns an observable recovery error into data-loss risk.

## 21. Testing the pre-deserialization strategy

### 21.1. Valid cases

1. Valid JSON payload matching current schema.
2. Valid payload matching an older still-supported schema version.
3. Complete headers with proper encoding.
4. Record near the size limit without exceeding it.
5. Valid tombstone if permitted by the topic.

### 21.2. Invalid data cases

1. Empty payload and null on topics forbidding tombstones.
2. Payload exceeding the size limit.
3. Syntactically broken JSON that starts with `{`.
4. Content-type header claiming JSON while payload is binary.
5. Malformed UTF-8.
6. Confluent framing with truncated bytes or wrong magic byte.
7. Invalid schema ID.
8. Deeply nested JSON or oversized strings exceeding parser constraints.
9. Key deserialization failure.

### 21.3. Infrastructure cases

1. Temporary Registry timeout: bounded retry.
2. Registry returns nonexistent schema: classified per contract.
3. DLT broker or ACL rejects publish: source record not falsely marked lost/committed.
4. Consumer restarts after failure and record is redelivered.
5. Rebalance mid-retry and recovery.
6. Producer switches serializer during a rolling update.

### 21.4. What to observe in tests

- Whether the listener was invoked (error before vs. after Kafka deserializer).
- Exception types and cause chains.
- Whether the record was retried or routed to DLT per policy.
- Whether the DLT retained key, value/raw bytes, and source metadata.
- Whether group offset commits accurately post-recovery.
- Whether idempotency blocks duplicate side effects on redelivery.

Tests must assert real data outcomes and offsets, not merely how many times a logger was called.

## 22. Designing boundaries of responsibility

To keep systems operable, split responsibilities clearly:

| Component | Responsibility |
|---|---|
| Producer contract | Emit data matching format/schema, retain event ID |
| Wire preflight | Check bytes, framing, metadata, and resource budgets |
| Deserializer/codec | Parse bytes into objects, check encoding/format |
| Schema validator | Check structure and compatibility |
| Business validator | Check business rules and state |
| Error handler | Classify exceptions, retry/backoff/recovery |
| DLT/quarantine | Retain unprocessable records for investigation |
| Observability | Metrics/logs/traces by error and impact |
| Replay workflow | Reintroduce records once root causes are fixed |

Never let the preflight layer call business APIs or update databases before decoding the record. Preflight should be cheap and side-effect-free to stay safe even on malformed/untrusted bytes.

## 23. Operations checklist

### Format and preflight

- [ ] Topic contract states serialization format, size limits, tombstone policy, and schema versions.
- [ ] Right preflight point chosen: raw `byte[]` listener or custom Kafka deserializer.
- [ ] Preflight does not falsely assume every JSON starts immediately at `{` or every binary shares one magic byte.
- [ ] Headers are validated per contract without being treated as unconditionally trustworthy.
- [ ] Limits enforced on size, parser depth, and valid event types.

### Error handling

- [ ] `ErrorHandlingDeserializer` present if custom Kafka deserializer can throw before the listener.
- [ ] Malformed data and Registry/network errors classified separately.
- [ ] Bounded retries/backoff; no retry storms on permanently invalid payloads.
- [ ] DLT producer supports raw bytes and domain objects per recovery path.
- [ ] DLT publish failures never cause erroneous source offset commits.

### Reliability

- [ ] Event IDs and source metadata preserved across DLT/replay.
- [ ] Consumer is idempotent when Kafka redelivers records.
- [ ] Tombstones handled per dedicated policy.
- [ ] Schema evolution has backward-compatibility tests.
- [ ] Replay is rate-limited with outcome reconciliation.

### Observability and security

- [ ] Metrics exist for reject rate, deserialization failures, registry timeouts, lag, and DLT.
- [ ] Logs capture stage, reason, and topic/partition/offset without exposing sensitive payloads.
- [ ] Event ID/offset never used as metric tags.
- [ ] Runbooks exist for poison pills and DLT serialization errors.
- [ ] ACLs, encryption, retention, and quarantine/DLT access are governed.

## Conclusion

Pre-deserialization data validation is a defensive layer helping Spring Kafka consumers catch payloads violating wire-format contracts and resource budgets before constructing domain objects. It can be implemented with `ByteArrayDeserializer` followed by validation/decoding inside the listener, or with a custom Kafka `Deserializer` paired with `ErrorHandlingDeserializer` so pre-listener failures still have a safe handling path. Useful checks include size, tombstones, framing, magic bytes, schema IDs, content types, and integrity, yet they do not replace parsers, schema validation, or business rules. Separate permanent data errors from transient infrastructure failures, preserve raw payloads for the DLT, commit only after safe recovery, and monitor lag/exceptions/recovery so a single bad record never turns into a lingering poison pill on the consumer group.
