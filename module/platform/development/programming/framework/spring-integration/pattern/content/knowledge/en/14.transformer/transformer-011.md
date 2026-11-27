# Content-Type-Based Transformer

> **Chapter:** Transformer  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation while testing and monitoring processing branches. This lesson focuses on **selecting a transformation based on content type (`Content-Type`)** while preserving message contracts and business semantics.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain which **data representation** `Content-Type` describes, distinguishing it from the payload's Java type and the business event type.
2. Select transformers for JSON, plain text, or other supported media types **without guessing formats** from arbitrary payload bytes.
3. Enforce `contentType`, `charset`, contract version, byte payloads, validation, and size limits under a **fail-closed** policy.
4. Write a pure Java mapper and wire it into a Spring Integration `Transformer` / Java DSL flow.
5. Understand how **converting a payload from `byte[]` to a DTO** affects the meaning of the `contentType` header, correlation, and related metadata.
6. Test format selection, accurate value mapping, missing/invalid headers, malformed payloads, charsets, technical errors, and sync–async boundaries.

## 2. Context: One Endpoint, Multiple Data Encodings

A platform receives orders from integrators with varying capabilities. Newer partners send JSON; a legacy system sends a single text line under a published internal protocol. Both must produce the exact same `CanonicalOrder` before entering Routers and business handlers.

First message:

~~~http
Content-Type: application/json; charset=UTF-8
X-Contract-Version: v1

{"orderId":"ORD-501","currency":"USD","amountMinor":125050}
~~~

Second message:

~~~http
Content-Type: text/plain; charset=UTF-8
X-Contract-Version: v1

ORD-502|USD|125050
~~~

In the **illustrative text protocol**, `|` separates exactly three fields: order ID, currency, and amount in minor units (cents). Pipe characters inside order IDs, escaping, and multi-line records are unsupported. If a real system handles complex text/CSV, use a compliant parser rather than `split`.

Both map to:

~~~json
{
  "orderId": "ORD-501",
  "currency": "USD",
  "total": 1250.50
}
~~~

In Java, `total` will be `BigDecimal("1250.50")`, not a floating-point `double`.

~~~mermaid
flowchart LR
    A["Inbound adapter: byte[]"] --> V["Check Content-Type, charset, version"]
    V --> T{"Content-Type Transformer"}
    T -->|"application/json"| J["JSON parser"]
    T -->|"text/plain"| P["Contract v1 text parser"]
    T -->|"Other"| E["Reject / error flow"]
    J --> C["CanonicalOrder"]
    P --> C
    C --> R["Router / business handler"]
~~~

**Key focus:** `Content-Type` determines **how to interpret bytes**, not which business consumer handles the order. Once converted into a canonical DTO, a Router can use business data to select branches.

## 3. Distinguishing Three Frequently Conflated Concepts

| Concept | Determined By | Examples | Role |
| --- | --- | --- | --- |
| **Media type / Content-Type** | Transport contract or verified message metadata | `application/json`, `text/plain`, `application/xml` | Chooses how to decode the representation |
| **Payload Java type** | Adapter, deserializer, or prior Transformer | `byte[]`, `String`, `PartnerOrder` | Determines Java APIs and JVM handling |
| **Business message type** | Domain schema/contract | `OrderCreated`, `CancelOrder` | Selects business rules/Router branch |

A `byte[]` may contain JSON, XML, Protobuf, or compressed bytes. Checking `payload instanceof byte[]` is therefore **insufficient** to choose a parser.

Conversely, an adapter may have already deserialized JSON into `OrderRequest` before the message enters Spring Integration; in that case, do not parse JSON a second time just because `contentType` still reads `application/json`.

A business message of type `CancelOrder` might also be encoded in JSON **or** Protobuf. Hence, **"transforming by content type" is not synonymous with "routing by business event type."**

### 3.1. The `contentType` Header in Spring Messaging

`MessageHeaders.CONTENT_TYPE` is the constant for the standard `contentType` header name in Spring Messaging. Its value can be a `MimeType` or a MIME type string depending on the adapter and message builder. For example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<byte[]> incoming = MessageBuilder.withPayload(
        "{\"orderId\":\"ORD-501\"}".getBytes(
            java.nio.charset.StandardCharsets.UTF_8))
    .setHeader(MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.parseMimeType("application/json;charset=UTF-8"))
    .build();
~~~

This message only illustrates setting the header; the JSON payload intentionally lacks fields required by this lesson's order contract and **cannot yet be converted into a valid `CanonicalOrder`**.

When input arrives over HTTP, the HTTP request's `Content-Type` normally needs to be mapped by the adapter into `MessageHeaders`; never assume every external header automatically survives every step.

### 3.2. `Content-Type` Differs from `Content-Encoding`

`Content-Type: application/json` identifies the data format; `Content-Encoding: gzip` identifies a transport-layer compression encoding. You cannot feed gzip-compressed bytes straight into a JSON parser and conclude `Content-Type` was wrong.

A proper design requires a **controlled decompression/decoding step** before the parser if the contract allows compression, along with decompressed size limits to guard against small payloads expanding massively.

### 3.3. `Content-Type` Differs from `charset`

`application/json;charset=UTF-8` carries both the media type and a charset parameter. For a UTF-8-only contract, accept valid UTF-8 as specified and **reject other charsets** instead of falling back to the host's default encoding.

When charset is omitted, default to UTF-8 only if **the transport/schema contract explicitly specifies it**. In this lesson, contract v1 specifies UTF-8 even when the charset parameter is absent.

## 4. Transformer Selection Table by Media Type

| Content-Type | Expected Format | Handling | Example Behavior |
| --- | --- | --- | --- |
| `application/json` | JSON v1 | Jackson JSON parser + validation | **Supported** |
| `application/json;charset=UTF-8` | JSON v1 UTF-8 | Same parser | **Supported** |
| `text/plain` | Single line `ID|CURRENCY|MINOR` v1 | Contract v1 text parser | **Supported** |
| `text/plain;charset=UTF-8` | Text protocol v1 UTF-8 | Same parser | **Supported** |
| `application/xml` | XML | Needs XML mapper and XXE-hardened parser | **Unsupported in sample code** |
| `text/csv` | CSV | Needs proper CSV parser with escaping/quoting | **Unsupported in sample code** |
| `application/protobuf` | Protobuf | Needs concrete schema/message type and decoder | **Unsupported in sample code** |
| `application/vnd.company.order+json` | Vendor JSON | Must be explicitly approved by contract and version | **Not accepted automatically** |
| Missing `contentType` | Unknown representation | Never guess a parser | **Rejected** |
| `application/json;charset=ISO-8859-1` | JSON with wrong contract encoding | Never silently transcode | **Rejected** |

This table **does not imply JSON is the right default for every system**. Applications can support XML, Avro, CBOR, Protobuf, or CSV via dedicated Transformers once explicit protocols and schemas exist.

### 4.1. Exact Match or `application/*+json`?

Some media types carry a `+json` suffix while defining completely different contracts. For instance, `application/vnd.vendorA.order+json` and `application/vnd.vendorB.order+json` are both JSON yet may use different field names, currency units, and enums.

Do not route all `+json` media types into one business mapper unless schemas are confirmed compatible. You can separate concerns:

~~~text
Media type → technical parser → versioned DTO → business mapper
~~~

In multi-partner applications, an allowlisted registry keyed by **media type + contract version + verified source** is safer than a check like `subtype.endsWith("+json")`.

### 4.2. When `Content-Type` Does Not Match the Body

If the header declares JSON while the body is XML, the JSON parser must fail **in a controlled manner**. Never fall back from JSON to XML, CSV, and text until some parser succeeds. Trying every format creates ambiguous contracts and opens security flaws from parser differential bugs.

## 5. Business Mapping Table to Canonical DTO

The **v1 contract of this lesson** supports only `USD` orders with `amountMinor` in cents and positive `total`. Both JSON and text must therefore obey:

| Canonical Field | JSON v1 | Text v1 | Condition |
| --- | --- | --- | --- |
| `orderId: String` | `orderId` | Part 1 | Non-`null`, non-blank |
| `currency: String` | `currency` | Part 2 | Exactly `USD` |
| `total: BigDecimal` | `amountMinor` | Part 3 | Positive integer, cents → USD |
| `schemaVersion` | Header `contractVersion` | Header `contractVersion` | Must be `v1` |

**Never use `double` for money.** For `amountMinor=125050`, the exact conversion is:

~~~java
import java.math.BigDecimal;

BigDecimal total = BigDecimal.valueOf(125050L, 2);
System.out.println(total.toPlainString()); // "1250.50"
~~~

Scale 2 is **specific to USD in this example**; never generalize it blindly across all currencies or payment systems.

### 5.1. Missing Values Must Not Become Valid Defaults

If JSON omits `currency` or text contains `ORD-502||125050`, the Transformer must emit a mapping error—never insert `USD` just because most traffic uses USD.

If input omits `amountMinor`, calling defaulting APIs like `JsonNode.asLong()` without type checks turns missing fields into `0` or coerced guesses. Check that **the node exists, is an integral number, and fits within `long`** before converting.

### 5.2. Schema Version Must Be Explicit

Under the same `application/json`, v2 might replace `amountMinor` with `amountDecimal` or nest `currency` into an object. A v1 Transformer must not silently proceed with default values.

A safe approach keys selection on `(mediaType, contractVersion)`. When upgrading, add a v2 mapper and compatibility tests rather than altering v1 in a way that breaks older queued messages.

## 6. Pure Java: Mapper by `Content-Type` and Contract Version

The example uses **Java 17+**, **Spring Messaging**, and Jackson Databind. In a real Spring Boot/Spring Integration application, declare Jackson dependencies compatible with your stack. The code below is the **mapper core**, excluding outbound adapters or real HTTP transport.

### 6.1. Canonical DTO and Coded Mapping Failures

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record CanonicalOrder(String orderId,
                      String currency,
                      BigDecimal total) {
    CanonicalOrder {
        if (orderId == null || orderId.isBlank()) {
            throw new MappingFailure("ORDER_ID_MISSING");
        }
        if (!"USD".equals(currency)) {
            throw new MappingFailure("UNSUPPORTED_CURRENCY");
        }
        if (total == null || total.signum() <= 0) {
            throw new MappingFailure("INVALID_TOTAL");
        }
    }
}

final class MappingFailure extends RuntimeException {
    private final String code;

    MappingFailure(String code) {
        super(code);
        this.code = code;
    }

    MappingFailure(String code, Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

The canonical model holds a **normalized** monetary amount. `MappingFailure` separates data/contract errors from downstream failures like connection timeouts. In production, you can attach source/schema version, error category, correlation ID, and field location **without sensitive data**.

### 6.2. Reading and Validating MIME Type Before Parsing

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

final class ContentTypeOrderMapper {
    private static final int MAX_BYTES = 64 * 1024;
    private final ObjectMapper json = new ObjectMapper();

    CanonicalOrder decode(Message<?> message) {
        if (message == null || !(message.getPayload() instanceof byte[] bytes)) {
            throw new MappingFailure("PAYLOAD_MUST_BE_BYTES");
        }
        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new MappingFailure("PAYLOAD_SIZE_INVALID");
        }

        MimeType type = parseContentType(
            message.getHeaders().get(MessageHeaders.CONTENT_TYPE));

        if (!"v1".equals(message.getHeaders().get("contractVersion"))) {
            throw new MappingFailure("UNSUPPORTED_CONTRACT_VERSION");
        }

        if (type.getCharset() != null
                && !StandardCharsets.UTF_8.equals(type.getCharset())) {
            throw new MappingFailure("UNSUPPORTED_CHARSET");
        }

        // Strict decoder: do not silently replace invalid UTF-8 bytes with U+FFFD.
        String content = strictUtf8(bytes);

        if (is(type, "application", "json")) {
            return decodeJson(content);
        }
        if (is(type, "text", "plain")) {
            return decodeTextV1(content);
        }
        throw new MappingFailure("UNSUPPORTED_CONTENT_TYPE");
    }

    static MimeType parseContentType(Object header) {
        try {
            if (header instanceof MimeType mime) {
                return mime;
            }
            if (header instanceof String value) {
                return MimeTypeUtils.parseMimeType(value);
            }
        } catch (IllegalArgumentException ex) {
            throw new MappingFailure("INVALID_CONTENT_TYPE", ex);
        }
        throw new MappingFailure("CONTENT_TYPE_MISSING");
    }

    private static boolean is(MimeType mime, String type, String subtype) {
        return type.equalsIgnoreCase(mime.getType())
            && subtype.equalsIgnoreCase(mime.getSubtype());
    }

    private static String strictUtf8(byte[] bytes) {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
        } catch (CharacterCodingException ex) {
            throw new MappingFailure("INVALID_UTF8", ex);
        }
    }

    private CanonicalOrder decodeJson(String text) {
        try {
            JsonNode root = json.readTree(text);
            if (root == null || !root.isObject()) {
                throw new MappingFailure("JSON_OBJECT_REQUIRED");
            }

            String orderId = requiredText(root, "orderId");
            String currency = requiredText(root, "currency");
            JsonNode minor = root.get("amountMinor");

            if (minor == null || !minor.isIntegralNumber()
                    || !minor.canConvertToLong()) {
                throw new MappingFailure("AMOUNT_MINOR_INVALID");
            }

            return fromMinorUnits(orderId, currency, minor.longValue());
        } catch (JsonProcessingException ex) {
            throw new MappingFailure("MALFORMED_JSON", ex);
        }
    }

    private static String requiredText(JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw new MappingFailure("INVALID_" + field.toUpperCase(Locale.ROOT));
        }
        return value.textValue();
    }

    private static CanonicalOrder decodeTextV1(String text) {
        // Strictly for text v1 contract: exactly three fields, no escaping.
        String[] fields = text.split("\\|", -1);
        if (fields.length != 3) {
            throw new MappingFailure("TEXT_FIELD_COUNT_INVALID");
        }

        long minor;
        try {
            minor = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new MappingFailure("AMOUNT_MINOR_INVALID", ex);
        }
        return fromMinorUnits(fields[0], fields[1], minor);
    }

    private static CanonicalOrder fromMinorUnits(
            String id, String currency, long minor) {
        if (minor <= 0) {
            throw new MappingFailure("AMOUNT_MINOR_INVALID");
        }
        return new CanonicalOrder(
            id, currency, java.math.BigDecimal.valueOf(minor, 2));
    }
}
~~~

This is a **narrow, intentional parser**:

- Accepts only `byte[]` payloads; never tries to deserialize an unexpected `Map`, `String`, or DTO from another adapter.
- Rejects empty bodies or payloads over 64 KiB before decoding, using a demo threshold (production sets limits per contract).
- Requires `contractVersion=v1`; v2 is not supported yet.
- Accepts UTF-8 only: configures the decoder with `CodingErrorAction.REPORT` so invalid byte sequences fail instead of losing data.
- Accepts strictly `application/json` or `text/plain` per contract; other MIME types are rejected.
- JSON must be an object with an integral `amountMinor`; text must have exactly three fields.
- Does not silently strip whitespace from IDs or currencies. If the contract requires trimming/normalizing, define that rule consistently across **both parsers**.

### 6.3. Parser Security Considerations

This example parses only JSON and text. If adding XML, harden the parser against **XXE**, disabling unnecessary external entities/DTDs and setting resource limits. If adding CSV, use a parser supporting quoting, escaping, multi-line fields, and size bounds; `split(",")` is not a general CSV parser.

Likewise, a syntactically valid JSON document **is not necessarily schema-valid**. Production contracts may require JSON Schema, field limits, versioning, object depth caps, and rejecting disallowed fields. The sample Jackson parser reads three required fields and ignores extra ones; if your system requires a **strict schema**, add a step rejecting out-of-contract fields.

## 7. Spring Integration: Writing a Header-Aware Message Transformer

A Spring Integration Transformer can inspect both **payload and headers** to decide how to convert. A clean pattern is extending `AbstractTransformer`, overriding `doTransform(Message<?>)`, calling the mapper, and returning a **message carrying the canonical DTO**.

### 7.1. Why Update the `contentType` Header?

Once the payload changes from JSON/text bytes to `CanonicalOrder`, leaving `contentType=application/json` on the internal message can mislead a downstream consumer into treating the payload as unparsed JSON.

In the example, we:

1. Preserve business correlation headers and source version.
2. Remove `MessageHeaders.CONTENT_TYPE` because the payload is now an **unserialized canonical Java object**.
3. Set `originalContentType` for provenance and `canonicalSchemaVersion` so downstream knows the current contract.

~~~java
import org.springframework.integration.transformer.AbstractTransformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

final class ContentTypeOrderTransformer extends AbstractTransformer {
    private final ContentTypeOrderMapper mapper;

    ContentTypeOrderTransformer(ContentTypeOrderMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    protected Object doTransform(Message<?> message) {
        CanonicalOrder order = mapper.decode(message);
        String sourceType = ContentTypeOrderMapper
            .parseContentType(message.getHeaders()
                .get(MessageHeaders.CONTENT_TYPE))
            .toString();

        return MessageBuilder.withPayload(order)
            .copyHeaders(message.getHeaders())
            .removeHeader(MessageHeaders.CONTENT_TYPE)
            .setHeader("originalContentType", sourceType)
            .setHeader("canonicalSchemaVersion", "v1")
            .build();
    }
}
~~~

When a Transformer returns a `Message<?>`, Spring Integration uses the returned message per endpoint semantics. The example uses `MessageBuilder` to control application headers. **Do not rely on envelope object identity** for idempotency or assume every header from an external adapter automatically survives into another system.

In production, `originalContentType` is purely diagnostic/trace metadata. Never treat it as verified proof of origin: the original MIME header may be client-supplied and must be checked against transport, permissions, and schema.

### 7.2. Java DSL Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ContentTypeTransformerConfiguration {

    @Bean
    ContentTypeOrderMapper contentTypeOrderMapper() {
        return new ContentTypeOrderMapper();
    }

    @Bean
    ContentTypeOrderTransformer contentTypeOrderTransformer(
            ContentTypeOrderMapper mapper) {
        return new ContentTypeOrderTransformer(mapper);
    }

    @Bean("orders.raw.in")
    DirectChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean("orders.canonical.out")
    QueueChannel canonicalOutput() {
        // Internal queue serving as sink for this lesson and integration tests.
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeIncomingOrders(
            ContentTypeOrderTransformer transformer) {
        return IntegrationFlow.from("orders.raw.in")
            .transform(transformer)
            .channel("orders.canonical.out")
            .get();
    }
}
~~~

~~~text
orders.raw.in (DirectChannel)
    |
    v
ContentTypeOrderTransformer
    |-- read Content-Type + contractVersion
    |-- JSON/text v1 parser → CanonicalOrder
    |-- remove old contentType header, attach canonicalSchemaVersion
    v
orders.canonical.out (QueueChannel in demo)
    |
    v
Router/handler/outbound adapter in real system
~~~

`QueueChannel` at the demo output only collects messages for testing; there is no consumer forwarding to a warehouse, CRM, or payment system yet. Before production, add endpoints consuming the canonical DTO with matching delivery and error policies.

### 7.3. Example Sending a Message

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

String json = """
    {"orderId":"ORD-501","currency":"USD","amountMinor":125050}
    """;

Message<byte[]> raw = MessageBuilder
    .withPayload(json.getBytes(StandardCharsets.UTF_8))
    .setHeader(MessageHeaders.CONTENT_TYPE,
        "application/json;charset=UTF-8")
    .setHeader("contractVersion", "v1")
    .setHeader("businessCorrelationId", "ORD-501")
    .build();

// inputChannel is the injected orders.raw.in bean.
// inputChannel.send(raw);
~~~

If your adapter already produced a `String` or DTO instead of `byte[]`, do not send that message straight into the flow above. Establish **one clear boundary**: either the adapter supplies bytes for MIME-based transformation, or the adapter decodes into a concrete type and the flow continues from there. Avoid parsing twice.

## 8. Multi-Format Architecture: One Transformer or Many?

The example used **one Transformer dispatching internally** because there were only two simple formats and one target DTO. Several valid strategies exist:

| Strategy | How It Works | When to Use |
| --- | --- | --- |
| Single Transformer dispatching by MIME | One endpoint reads `Content-Type` and calls the matching parser | Few formats, shared canonical model, small logic |
| Content-Type Router before specialized Transformers | Router selects JSON/XML/Protobuf channels, each with its own mapper | Many formats, complex parsers, per-format error observability needed |
| Controlled parser registry | Look up parser/mapper by `(mediaType, version)` | Many partners/versions, frequent format additions |
| Adapter deserializes before flow | HTTP/broker adapter turns bytes into DTOs | Simple transport contract; keep MIME out of business flows |

~~~mermaid
flowchart LR
    IN["bytes + validated contentType"] --> CR{"Content-Type Router"}
    CR -->|JSON v1| J["JSON Transformer"]
    CR -->|XML v2| X["XML Transformer"]
    CR -->|Protobuf v1| P["Protobuf Transformer"]
    J --> CAN["Canonical DTO / validation"]
    X --> CAN
    P --> CAN
~~~

In the Router-before-Transformers design, **routing by `Content-Type` selects only the parser**; once a canonical DTO exists, a separate Business Router decides where the domain object goes for processing.

**Never** derive channel names straight from a sender-supplied `Content-Type` header. Map validated media types through an **allowlist**, never letting clients pick arbitrary beans or channels.

## 9. Type Conversion vs. Schema Translation

Deserializing a JSON message into `Map<String,Object>` and converting it to `CanonicalOrder` is in-JVM **type mapping**. By contrast, mapping `amount_minor` to `total` with currency scales and business rules is **schema/semantic translation**.

Spring Integration offers Transformers, conversion services, and serializers/deserializers. Pick tools by responsibility:

- **Deserializer/codec:** turns bytes into a source representation object.
- **Schema mapper:** converts the source object into a canonical DTO or target object.
- **Header Enricher:** adds metadata like schema version or verified tenant.
- **Filter:** blocks ineligible messages.
- **Router:** selects destinations/branches by format or business rules.
- **Gateway/Adapter:** communicates with transports and external systems.

A pipeline might look like:

~~~text
Inbound adapter (bytes)
  → Validate Content-Type / schemaVersion
  → JSON/XML/Text parser (Transformer)
  → Source DTO
  → Canonical schema mapper (Transformer)
  → Enrich metadata if external lookup is needed
  → Business Router
  → Handler / Outbound Gateway
~~~

Not every step requires a separate channel, though each responsibility should have its own **contract, testability, and error handling**.

## 10. Source Metadata, Type Errors, and Trust Boundaries

### 10.1. Do Not Trust Sender MIME Headers as Security Proof

`Content-Type` is a **representation declaration**, not proof of identity, tenant, or authorization. An external request can claim `application/json` while sending non-JSON bytes; the parser catches the syntax error. Even so, that does not prove the sender is allowed to submit that event type.

Verify at ingress:

1. Authentication, signatures, mTLS, or appropriate protection.
2. Check account/tenant permissions against **allowed content types and versions**.
3. Enforce message size limits and parsing timeouts.
4. Never let MIME values select paths to internal endpoints directly.
5. Never trust client-supplied "verified" headers.

### 10.2. Missing or Invalid `Content-Type`

Under this contract:

- Missing header → `CONTENT_TYPE_MISSING`.
- Invalid MIME syntax → `INVALID_CONTENT_TYPE`.
- Unsupported MIME → `UNSUPPORTED_CONTENT_TYPE`.
- Charset other than UTF-8 → `UNSUPPORTED_CHARSET`.
- Invalid UTF-8 bytes → `INVALID_UTF8`.
- Broken JSON → `MALFORMED_JSON`.
- Missing or wrong schema version → `UNSUPPORTED_CONTRACT_VERSION`.

Separating error codes lets operators distinguish **sender contract violations** from **infrastructure failures**. If an inbound adapter blocks unsupported MIME types before reaching the Transformer, that layer must emit errors/replies matching the same contract.

### 10.3. Avoid Mutating Shared Payloads Accidentally

Messages inside a JVM can share payload references. If a Transformer receives a mutable `Map` and edits its entries in place, another recipient may observe mutated data. Producing an **immutable canonical DTO** without mutating inbound payloads is much easier to test safely.

For `byte[]`, byte arrays are mutable; a producer could modify the array after queuing. At async boundaries, ensure **immutable snapshots/intentional copies** if you cannot guarantee the producer stops mutating the array.

## 11. Error Handling and Multi-Branch Behavior

### 11.1. Transformer Error Paths

A Transformer can encounter:

| Error Type | Example | Handling Approach |
| --- | --- | --- |
| Malformed payload | Broken JSON quotes, wrong text column count | Reject/quarantine per contract |
| Unsupported Content-Type/version | XML sent to a JSON/text-only flow | Never auto-try another parser |
| Semantic validation | Amount ≤ 0, blank order ID | Reject with reason code |
| Mapper bug | Unexpected `NullPointerException` | Technical error: alert and investigate |
| External failure after Transformer | HTTP 503 when sending canonical DTO | Retry/error at outbound Gateway; do not blame MIME |
| Redelivery | Same event delivered again | Idempotent handler; prevent duplicate side effects |

With `DirectChannel`, Transformer errors can propagate back to the caller (typically wrapped by Spring Integration/Messaging). With pollers, executors, or brokers, errors may surface later as an `ErrorMessage` sent to an error channel per configuration.

**Never** assume every parser error should auto-retry: broken JSON cannot "heal itself" when re-sending identical bytes. Conversely, external I/O errors can use bounded retries under a separate policy.

### 11.2. Request–Reply Gateways

If a synchronous Gateway waits for `CanonicalOrder` or a business outcome, a failing Transformer or rejection branch must produce a **controlled exception/reply**. Never just drop the message and leave the caller hanging until timeout when the protocol expects an error response.

If input arrives from Kafka or an async queue, retry, dead-letter, and ack/nack decisions belong in the consumer/adapter contract without infinite loops.

### 11.3. Retries, Correlation, and Idempotency

A bytes → DTO mapping **causes no side effects** and can be safely recomputed. When that DTO is dispatched to **create an order**, however, side effects may already have occurred before a timeout. Use stable idempotency keys such as `(sourceSystem, orderId, operation)` or `commandId` rather than a fresh message ID generated on each retry.

`businessCorrelationId` stitches traces across Transformers; it **does not replace** idempotency. If Splitter/Aggregator follows the canonical DTO, preserve or assign correlation/sequence metadata per contract so distinct orders never merge accidentally.

## 12. Testing the Standalone Java Mapper

Before testing with a Spring context, unit tests should prove **right parser selection** and **right canonical values**.

### 12.1. JUnit 5 Parameterized Tests for JSON and Text

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.math.BigDecimal;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class ContentTypeOrderMapperTest {
    private final ContentTypeOrderMapper mapper =
        new ContentTypeOrderMapper();

    private static Message<byte[]> message(String contentType, String body) {
        return MessageBuilder
            .withPayload(body.getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, contentType)
            .setHeader("contractVersion", "v1")
            .build();
    }

    static Stream<Arguments> validRepresentations() {
        return Stream.of(
            Arguments.of(
                "application/json;charset=UTF-8",
                "{\"orderId\":\"ORD-501\",\"currency\":\"USD\","
                    + "\"amountMinor\":125050}",
                "ORD-501"),
            Arguments.of(
                "text/plain;charset=UTF-8",
                "ORD-502|USD|125050",
                "ORD-502")
        );
    }

    @ParameterizedTest
    @MethodSource("validRepresentations")
    void mapsDifferentContentTypesIntoSameCanonicalContract(
            String type, String body, String expectedId) {
        CanonicalOrder order = mapper.decode(message(type, body));

        assertEquals(expectedId, order.orderId());
        assertEquals("USD", order.currency());
        assertEquals(new BigDecimal("1250.50"), order.total());
    }
}
~~~

These tests prove the same canonical schema can be produced from two representations. In production, add **full schema tests** covering unknown fields, enums, required/null fields, and parser resource limits.

### 12.2. Required Negative Tests

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class ContentTypeOrderMapperNegativeTest {
    private final ContentTypeOrderMapper mapper =
        new ContentTypeOrderMapper();

    private Message<byte[]> input(String mime, String body) {
        return MessageBuilder.withPayload(
                body.getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, mime)
            .setHeader("contractVersion", "v1")
            .build();
    }

    @Test
    void rejectsUnsupportedMediaTypeInsteadOfGuessingByBody() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input(
                "application/xml",
                "{\"orderId\":\"ORD-501\",\"currency\":\"USD\","
                    + "\"amountMinor\":125050}")));

        assertEquals("UNSUPPORTED_CONTENT_TYPE", ex.code());
    }

    @Test
    void rejectsJsonWithNonIntegralMinorUnits() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input("application/json",
                "{\"orderId\":\"ORD-501\",\"currency\":\"USD\","
                    + "\"amountMinor\":12.50}")));

        assertEquals("AMOUNT_MINOR_INVALID", ex.code());
    }

    @Test
    void rejectsWrongTextFieldCount() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input("text/plain", "ORD-501|USD")));

        assertEquals("TEXT_FIELD_COUNT_INVALID", ex.code());
    }

    @Test
    void rejectsMismatchedCharset() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input(
                "application/json;charset=ISO-8859-1",
                "{\"orderId\":\"ORD-501\"}")));

        assertEquals("UNSUPPORTED_CHARSET", ex.code());
    }

    @Test
    void rejectsMissingContractVersion() {
        Message<byte[]> m = MessageBuilder
            .withPayload("ORD-501|USD|125050".getBytes(
                StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, "text/plain")
            .build();

        MappingFailure ex = assertThrows(MappingFailure.class,
            () -> mapper.decode(m));
        assertEquals("UNSUPPORTED_CONTRACT_VERSION", ex.code());
    }
}
~~~

Also test **missing Content-Type**, empty `byte[]`, oversized payloads, invalid UTF-8, zero/negative amounts, `long` overflow, non-`USD` currencies, and non-object JSON.

### 12.3. Monetary Boundary Tests

| Input `amountMinor` | Expectation |
| --- | --- |
| `1` | `0.01` |
| `99` | `0.99` |
| `100` | `1.00` |
| `125050` | `1250.50` |
| `0` or negative | Rejected |
| Decimal `12.5` | Rejected because contract requires **integer cents** |
| JSON integer outside `long` range | Rejected instead of overflowing |

## 13. Integration Test: Checking Flow and Headers After the Transformer

Correct mapper unit tests **do not prove** Java DSL wiring is right. Integration tests send into `orders.raw.in`, receive from `orders.canonical.out`, and verify both the DTO and metadata.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ContentTypeTransformerConfiguration.class)
class ContentTypeTransformerFlowTest {
    @Autowired
    @Qualifier("orders.raw.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.canonical.out")
    PollableChannel output;

    @Test
    void transformsAndPreservesBusinessCorrelation() {
        String body =
            "{\"orderId\":\"ORD-601\",\"currency\":\"USD\","
                + "\"amountMinor\":125050}";

        Message<byte[]> raw = MessageBuilder
            .withPayload(body.getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
            .setHeader("contractVersion", "v1")
            .setHeader("businessCorrelationId", "ORD-601")
            .build();

        assertTrue(input.send(raw));

        Message<?> transformed = output.receive(1000);
        assertNotNull(transformed);
        assertInstanceOf(CanonicalOrder.class, transformed.getPayload());

        CanonicalOrder order =
            (CanonicalOrder) transformed.getPayload();

        assertEquals("ORD-601", order.orderId());
        assertEquals(new BigDecimal("1250.50"), order.total());

        assertEquals("ORD-601",
            transformed.getHeaders().get("businessCorrelationId"));
        assertEquals("v1",
            transformed.getHeaders().get("canonicalSchemaVersion"));
        assertNull(transformed.getHeaders().get(
            MessageHeaders.CONTENT_TYPE));

        assertNull(output.receive(0), "No duplicate canonical message");
    }
}
~~~

This test uses a `QueueChannel` as output **with no business consumer**. Because the flow from `DirectChannel` to the internal queue runs synchronously here, `receive(1000)` can inspect the output directly. It **does not** verify outbound HTTP/broker delivery or order creation.

If the output becomes an `ExecutorChannel` or broker, test with timeouts, handle concurrency, and wait for true completion events. If a Spring Test context reuses queues across test methods, reset or drain every test cleanly to avoid cross-test interference.

## 14. Comprehensive Test Matrix

| Test Group | Input | What to Verify |
| --- | --- | --- |
| JSON v1 | `application/json` + JSON bytes | Valid canonical DTO |
| Text v1 | `text/plain` + three fields | Valid canonical DTO |
| Omitted charset | Contract permits UTF-8 | Decodes as UTF-8 per spec |
| Non-UTF-8 charset | `charset=ISO-8859-1` | Rejected |
| MIME mismatches body | JSON MIME, text body | Does not fall back to another parser |
| Unsupported MIME | Unconfigured XML/CSV/Protobuf | Rejected with reason |
| Missing Content-Type | Header absent | Rejected; never guessed |
| Unsupported v2 version | Header version v2 | Rejected, or routed to v2 mapper once deployed |
| Mistyped header | `contentType` not `MimeType` or `String` | Rejected |
| Invalid UTF-8 | Broken byte sequence | Rejected; never silently replaced |
| Malformed JSON | Syntax error | `MALFORMED_JSON` |
| Wrong JSON type | `amountMinor` is string or float | Rejected |
| Wrong text column count | Missing or extra fields | Rejected |
| Monetary boundaries | 1, 100, 125050, 0, negative, overflow | No lost cents, no overflow |
| Oversized payload | Exceeds demo 64 KiB cap | Rejected early |
| Untrusted source header | Client-set `contractVersion` or tenant | Validated at ingress |
| Correlation | `businessCorrelationId` present | Carried on canonical message |
| Output header semantics | Payload is now a Java DTO | Does not retain misleading `application/json` |
| Mapper exception | Invalid input | No fake canonical message produced |
| Downstream timeout | Canonical already mapped | Retry/error at outbound handler; never blame parser |
| Command replay | Redelivery | Consumer produces no duplicate side effects |

**Note:** Some cases (ingress auth, real brokers, real serializers) cannot be proven by mapper unit tests. Write contract tests or end-to-end tests matching those boundaries.

## 15. Versioning and Compatibility as Formats Grow

Suppose in the future the system adds:

- JSON v2: `amountDecimal` replaces `amountMinor`.
- XML v1: a legacy partner supports only XML.
- Protobuf v1: high-traffic internal flows need binary schemas.
- Vendor media type: `application/vnd.example.order+json`.

Use a mapping registry table:

| Media Type | Contract Version | Parser/Mapper | Status |
| --- | --- | --- | --- |
| `application/json` | v1 | JSON v1 → `CanonicalOrder` | Supported |
| `text/plain` | v1 | Text v1 → `CanonicalOrder` | Supported |
| `application/json` | v2 | JSON v2 → `CanonicalOrder` | Enable only after tests |
| `application/xml` | v1 | XML v1 → `CanonicalOrder` | Enable only after hardening XML parser |
| `application/vnd.example.order+json` | v1 | Vendor JSON v1 mapper | Dedicated contract |

When deploying a new mapper, retain the old mapper while old messages remain in backlogs. Never change v1 parser semantics while older messages can still be replayed.

### 15.1. One Body Format, Multiple Distinct Schema Versions

`Content-Type: application/json` alone cannot distinguish `amountMinor` from `amountDecimal` contracts. When two versions share a media type, select using the **verified contract version**; avoid guessing versions via "parse whichever field exists" unless that is an explicitly approved and tested compatibility rule.

### 15.2. Watch Out for Unknown Fields

A JSON parser reading only required fields may ignore extra fields. While helpful for forward compatibility in some cases, it is dangerous if a new field **changes the meaning** of existing data—for example, adding `taxIncluded=false` changes what `total` means. Schema validation and consumer-driven contract tests must protect **semantics**, not only syntax.

## 16. Observability: Why Was This Parser Selected, and Did Conversion Succeed?

Suggested observation points in the flow:

| Observation Point | Data to Collect | Question |
| --- | --- | --- |
| Inbound adapter | Media type, byte size, verified source | Who sent it and in what format? |
| Contract gate | `contractVersion`, accepted/rejected, reason code | Is this version supported? |
| Transformer | Parser selected, latency, success/failure | Which format failed to parse? |
| Canonical validation | Invalid field/rule, line count, schema version | Does the canonical DTO satisfy the contract? |
| Downstream Router | Lane/decision, version | Which business branch received the message? |
| Outbound Adapter | Send result, retry, timeout | Did the message reach the external system? |
| Business consumer | Success/error/idempotency outcome | Was the order actually created? |

Use `ChannelInterceptor`, Wire Tap, metrics, and distributed tracing to observe stages. However:

- Never log raw bytes if payloads can carry PII, tokens, financial data, or untrusted content.
- Keep `mediaType`, `contractVersion`, `mappingResult`, and `errorCode` in metrics **allowlisted and low cardinality**.
- `orderId` and `businessCorrelationId` belong in access-controlled logs/traces, **not** as standard metric tags.
- Never treat `postSend(sent=true)` on an output queue as proof that external systems finished processing.
- Record the applied schema/mapping version or parser config if failures must be reproduced on replay.

## 17. Anti-Patterns to Avoid

| Anti-Pattern | Consequence | Fix |
| --- | --- | --- |
| Checking only `payload instanceof byte[]` and guessing JSON | `byte[]` can hold any format | Validate media type + schema version |
| Trying JSON, XML, then text until one parses | Ambiguous contracts, parser-confusion risks | Select parser from allowlist; fail closed |
| Confusing `Content-Type` with business event type | Selects wrong handler/owner | Separate parser selection from business routing |
| Ignoring charset and using host default encoding | Corrupted data and broken Unicode | Mandate UTF-8 and strict decoders |
| Using `double` for money | Precision and boundary bugs | Use `BigDecimal` with currency-appropriate scale |
| Using `split(",")` as a general CSV parser | Breaks on quotes, commas, and newlines | Use a proper CSV parser |
| Parsing XML without disabling DTD/external entities | XXE vulnerabilities and resource exhaustion | Harden XML parser + enforce resource limits |
| Keeping `contentType=application/json` on a DTO payload | Downstream tries to deserialize wrongly | Update/remove header reflecting the raw encoding |
| Granting authorization from `Content-Type` header | Clients can spoof metadata | Enforce AuthN/AuthZ and trust boundaries at ingress |
| Routing every vendor `+json` to the same mapper | Schemas/semantics may differ | Map by approved media type + version |
| Dropping parse errors silently without reason codes | Hard to debug or fix contracts | Route to error/quarantine channel with safe codes |
| Retrying malformed payloads infinitely | Wastes resources without fixing bad data | Reject/DLQ and classify errors |
| Treating Transformer pass as business completion | Downstream can still fail | Track business completion separately |
| Testing mapper while skipping integration/serialization tests | Channel wiring or JSON output may be broken | Test every contract boundary |

## 18. Pre-Deployment Checklist

- [ ] Supported media types and contract versions are explicitly documented.
- [ ] `contentType` header is mapped properly from transport and syntax-checked.
- [ ] Sender identity and permissions are verified **independently** of MIME headers.
- [ ] Policies exist for missing MIME, wrong charset, or body mismatching `Content-Type`.
- [ ] Parsers enforce byte/depth/time limits and defenses for XML, CSV, or compressed payloads if enabled.
- [ ] Mappers handle money, dates, enums, and nulls according to each schema's semantics.
- [ ] Canonical payloads are immutable or apply deliberate copying of mutable data.
- [ ] `Content-Type` header is updated or removed when representation changes from bytes to DTO.
- [ ] Correlation, schema version, and trace headers are preserved per boundary contract.
- [ ] Unit tests cover parsers/mappings and integration tests cover Transformers/channels.
- [ ] Serialization/contract tests verify real producer and consumer formats.
- [ ] Malformed data, unsupported contracts, mapper bugs, and downstream timeouts are clearly distinguished.
- [ ] Retry/idempotency is implemented on side-effecting consumers, never confused with parse errors.
- [ ] Metrics, logs, and error/DLQ stores never leak sensitive payloads.
- [ ] Plans exist to maintain v1 while rolling out v2 and replaying old messages.

## 19. Applied Exercise

A payment system receives `PaymentNotification` in two formats:

**JSON v1:**

~~~json
{
  "paymentId": "PAY-42",
  "currency": "USD",
  "amountMinor": 2505,
  "eventType": "AUTHORIZED"
}
~~~

**XML v1:**

~~~xml
<payment>
  <id>PAY-42</id>
  <currencyCode>USD</currencyCode>
  <minorAmount>2505</minorAmount>
  <kind>AUTHORIZED</kind>
</payment>
~~~

**Requirements:**

1. Define an immutable `CanonicalPayment` containing `paymentId`, `currency`, `amount`, and an `eventType` enum.
2. Write a JSON/XML v1 → canonical mapping table showing `amountMinor=2505` converting to `BigDecimal("25.05")`.
3. Select mappers by `(Content-Type, contractVersion)`; XML must never fall back to the JSON parser merely because fields share meaning.
4. Configure the XML parser against XXE with entity, depth, and resource limits.
5. Build a Spring Integration flow: inbound adapter → Transformer → Filter/Router → handlers per `eventType`.
6. Write positive/negative tests: JSON, XML, unsupported MIME, missing headers, wrong encoding, negative amounts, unknown enum, and malformed XML.
7. After converting to `CanonicalPayment`, how will you handle `contentType` and `businessCorrelationId`?
8. If `PaymentAuthorized` is redelivered twice, why is re-running the Transformer far less dangerous than downstream recording the payment twice? Propose an idempotency key and where to enforce it.

**Hint:** if JSON and XML share **the same business schema**, both parsers can produce equivalent source DTOs and feed the same canonical mapper. Still, verify mappings against real contracts—never guess XML field names or structure solely from `Content-Type`.

## 20. Summary

A **Content-Type-based Transformer** lets a single flow ingest multiple data representations and normalize them into a **consistent canonical schema**. The safe pipeline is **verify metadata/contract → select supported parser → decode safely → validate semantics → emit canonical payload → route business logic**. `Content-Type` specifies how to decode a message, **not** access permissions or business command types.

In Spring Integration, a Transformer can inspect `MessageHeaders.CONTENT_TYPE` and return a new DTO, while actively managing headers when representations change. To keep systems extensible and diagnosable, combine Filter, Enricher, Router, Gateway, Splitter/Aggregator, retry, error channel, correlation, idempotency, and testing from parsers to external adapters. Never test only "did it parse"; prove **right schema, right monetary amount, right version, right branch, and no duplicate side effects**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Message Translator, Content-Based Router, Canonical Data Model); Spring Integration documentation on Transformers, Message Channels, Java DSL, Error Handling, and Testing; Spring Messaging documentation on `MessageHeaders.CONTENT_TYPE`; Spring Framework documentation on `MimeType` and `MessageBuilder`; Jackson Databind and Java SE documentation on `BigDecimal` and `StandardCharsets`.
