# Serialization and the differences between data before and after conversion

In a message-based communication system, a **producer** might build a completely valid Java object while the **consumer** still fails to read the event. The root cause often lies in **serialization**: renamed fields, numeric precision loss, timestamps converted to a different format, `null` properties stripped, a mismatched `contentType` header, or incompatible serializers/deserializers on the two sides. **Spring Cloud Contract** helps specify and verify message exchange behavior, yet using it effectively requires knowing exactly how **data before conversion** differs from **data actually sent across the wire**.

This lesson belongs to the **Message contracts** chapter of the **SPRING_CLOUD_CONTRACT** module. The module uses **Groovy/YAML DSL** to write HTTP or messaging contracts, generates **producer tests**, publishes **stubs**, uses **Stub Runner** on consumers, and combines these steps in CI to catch incompatible API/event changes. Here the focus is on **domain object → Spring Message → wire payload → consumer object**, defining contract boundaries, and adding genuine serialization checks.

## 1. Four data layers in a message

Suppose **Order Service** emits an `OrderCreated` event so **Billing Service** can create an invoice. The data flow may look like this:

~~~mermaid
flowchart LR
    A["Domain event in Java"] --> B["Spring Message with payload + headers"]
    B --> C["Message converter / serializer"]
    C --> D["Broker: bytes + metadata"]
    D --> E["Consumer-side deserializer / converter"]
    E --> F["Consumer DTO / domain event"]
    F --> G["Business processing"]
~~~

| Layer | Example | What to pay attention to |
| --- | --- | --- |
| **In-memory producer object** | `OrderCreated("ORD-1042", 125000L, Instant...)` | Java types, getters/records, nulls, enums, object graphs. |
| **Spring Message** | `Message<OrderCreated>` with header `eventType=OrderCreated` | `payload` and `headers` are separate; message may not be serialized yet. |
| **Data on the wire** | UTF-8 JSON `byte[]` or Avro/Protobuf bytes | Field names, JSON types, timestamp/decimal representation, encoding, schema ID. |
| **Data after decoding** | `OrderCreatedV1` or Billing DTO | Field mapping, numeric types, dates/times, deserializer config, defaults. |

**A message on a broker is not the raw Java object.** An in-memory `Long` can become a JSON number; an `Instant` can become a timestamp string; `null` can serialize as `null` or disappear depending on configuration. Transport metadata such as Kafka keys, partitions, AMQP headers, or content type is also stored differently across transports and binders.

The two sides may even be written in different languages. Therefore, contracts should describe the **data shape and semantics exchanged between parties**, not merely the producer's internal class names.

## 2. A sample event before and after serialization

Let us choose a business event with a simple, stable structure:

| Field | Semantic type | Sample value |
| --- | --- | --- |
| `eventId` | Unique event ID (string) | `evt-00042` |
| `orderId` | Order ID (string) | `ORD-1042` |
| `amountMinor` | Monetary amount in minor units (integer) | `125000` |
| `occurredAt` | UTC timestamp per RFC 3339/ISO-8601 | `2026-01-15T10:20:30Z` |
| `note` | Optional note (string or null, per convention) | `null` |

The producer Java object might be:

~~~java
package com.acme.orders.events;

import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    long amountMinor,
    Instant occurredAt,
    String note
) {}
~~~

The producer creates an instance:

~~~java
OrderCreated event = new OrderCreated(
    "evt-00042",
    "ORD-1042",
    125000L,
    Instant.parse("2026-01-15T10:20:30Z"),
    null
);
~~~

If the serializer is configured to output ISO-8601 timestamps and **retain null fields**, the expected JSON payload is:

~~~json
{
  "eventId": "evt-00042",
  "orderId": "ORD-1042",
  "amountMinor": 125000,
  "occurredAt": "2026-01-15T10:20:30Z",
  "note": null
}
~~~

**This is the wire-format convention for this example**, not a promise that every Jackson setup produces this exact JSON. For instance, enabling `JsonInclude.Include.NON_NULL` can make `note` **disappear**; missing Java Time configuration can fail to serialize `Instant` or serialize it differently. Always inspect the **output of the serializer actually used in the real application**.

## 3. Spring Message, payload, headers, and broker data

In Spring, `org.springframework.messaging.Message<T>` is a **message envelope** holding `payload` and `headers`. Example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .setHeader("eventType", "OrderCreated")
    .setHeader("schemaVersion", 1)
    .build();
~~~

At this stage, `message.getPayload()` is still an **`OrderCreated` object**. It is not automatically a JSON string or a `byte[]`; conversion depends on the framework/binder/serializer executing at send time.

Illustrative snippet showing how a JSON codec converts the payload into bytes:

~~~java
byte[] payloadBytes = objectMapper.writeValueAsBytes(message.getPayload());
String text = new String(payloadBytes, StandardCharsets.UTF_8);
~~~

The snippet above only serializes the **payload**—it does not fold `MessageHeaders` into a JSON object. Headers like `eventType`, `schemaVersion`, and `contentType` are usually handled via transport metadata mechanisms. **Do not automatically infer** that they live inside the JSON body.

| Component | In this example | What to verify during implementation |
| --- | --- | --- |
| Message payload before conversion | `OrderCreated` | Is it a Java object, String, `byte[]`, or CloudEvent? |
| Message payload after conversion | JSON bytes | Matches expected serializer, charset, and schema? |
| `contentType` | `application/json` | How is the header represented on the broker and interpreted by consumer/binder? |
| `eventType` | `OrderCreated` | In transport headers or body? Which field does the consumer read? |
| `schemaVersion` | `1` | Number or string on the transport? Versioning rules? |
| Kafka key/partition, AMQP routing key | Transport-specific | Part of the committed interface or purely infrastructure config? |

If a producer creates a `Message<String>` already containing JSON, the framework might **serialize the String again** or treat it as raw text/bytes depending on content type and native encoding. Avoid bugs like **double serialization**: a JSON string `{"orderId":"ORD-1042"}` transmitted as a quoted, escaped **JSON string** instead of a **JSON object**.

## 4. Where does serialization alter data?

For JSON, changes can stem from serializers, annotations, naming strategies, formatters, or DTO types.

| Value before conversion | What it may become on the wire | Risk to consumer |
| --- | --- | --- |
| `Instant.parse("2026-01-15T10:20:30Z")` | ISO-8601 string or numeric timestamp | Consumer fails to parse or shifts timezone. |
| `BigDecimal("125000.00")` | JSON number `125000.00`, `125000`, or string | Loss of scale/monetary semantics, type-conversion failure. |
| Java `long amountMinor` | JSON number `125000` | Consumer uses narrower numeric type, overflows, or loses precision. |
| `enum OrderStatus.CREATED` | `"CREATED"` or customized value | Consumer fails to recognize enum after serializer change. |
| `String note = null` | `"note":null` or **missing `note` key** | Two states may carry different meanings. |
| Java field `orderId` | JSON `orderId` or `order_id` | Consumer binding misses field if naming strategy changes. |
| Collection/Map | JSON array/object | Array ordering, duplicates, nulls inside collection. |
| `byte[]` | Binary bytes, Base64 text inside JSON | Consumer confuses raw bytes with text/Base64. |

**Practical rule:** fields the consumer actually reads must be checked **at the communication boundary**. Comparing Java objects prior to serialization only tests in-memory objects; it does not prove JSON bytes or real broker messages honor the contract.

### 4.1. Missing object field vs. explicit null

Two distinct JSON payloads:

~~~json
{"orderId":"ORD-1042","note":null}
~~~

~~~json
{"orderId":"ORD-1042"}
~~~

In the first payload, `note` is **present** with JSON `null`; in the second, the `note` key is **absent**. If the event API specifies `null` as “note cleared” and an omitted key as “no update sent”, enabling `NON_NULL` can cause a **breaking change** even though `OrderCreated.note()` in Java remains `null`.

With Jackson `JsonNode`:

~~~java
JsonNode withNull = objectMapper.readTree(
    "{\"orderId\":\"ORD-1042\",\"note\":null}"
);
JsonNode withoutNote = objectMapper.readTree(
    "{\"orderId\":\"ORD-1042\"}"
);

assert withNull.has("note");
assert withNull.get("note").isNull();
assert !withoutNote.has("note");
~~~

`hasNonNull("note")` returns `false` for **both** cases, so never use it to test field presence. Especially for partial-update events, clearly define the distinction between **missing**, **null**, **empty string**, and **real values**.

### 4.2. Integers, floating-point numbers, and currency

JSON has a single **number** type, without distinguishing Java `long`, `int`, or `BigDecimal` by class name. Consumers may parse a JSON number as `Double`, `Long`, `BigDecimal`, or another runtime type.

For money, this example uses **`amountMinor=125000`** to avoid floating-point representations. When systems exchange decimal amounts, agree on **currency unit, scale, rounding rules, min/max bounds, and representation**. Never rely on a generic numeric regex and assume accounting precision is protected.

### 4.3. Timestamps, timezones, and precision

Three representations:

~~~text
2026-01-15T10:20:30Z
2026-01-15T17:20:30+07:00
2026-01-15T10:20:30.000Z
~~~

can refer to the same instant (depending on fractional seconds) yet are **different character strings**. Contracts must clarify whether consumers require the **same instant** or the **exact string format**. Switching from an ISO string to epoch milliseconds is usually a schema change even though both represent the same mathematical point in time.

### 4.4. Headers can be altered by converters or brokers

Not every header in `MessageHeaders` survives intact on the broker. Internal headers may be filtered, converted, or mapped by the binder. If consumers depend on `eventType`, `correlationId`, or `schemaVersion`, include them in **the contract and test them over a real transport**, not only in `MessageBuilder` prior to sending.

## 5. Groovy DSL for an output message contract

Suppose Order Service has a business operation that emits an event. The contract can live at `src/test/resources/contracts/messages/order_created.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    description 'Emit OrderCreated v1 for Billing Service'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-1042',
            amountMinor: 125000,
            occurredAt: '2026-01-15T10:20:30Z',
            note: null
        )
    }
}
~~~

This is a **message contract**, not an HTTP contract:

- `input.triggeredBy('publishOrderCreated()')` requires the generated producer test to invoke an **event-triggering method** on the base test class; that method must exist and match configuration.
- `outputMessage.sentTo('orders.created')` indicates the message **destination** according to the active messaging adapter's semantics.
- `headers` specifies metadata the consumer must read; actual names and types after mapping must be confirmed per binder/transport.
- `body` describes the **contract payload** expected by the receiver once processed by the appropriate converter. By itself, it **does not guarantee** raw bytes on Kafka/RabbitMQ match unless real serialization is verified.
- `label` is a convenient identifier for triggering messaging stubs; it is not synonymous with a broker topic or routing key.

**Version and adapter note:** this contract uses common Spring Cloud Contract messaging Groovy DSL constructs. Cross-check plugin capabilities, message verifiers/adapters, and binders in your **actual project version**—especially how `sentTo` maps to destinations, how `contentType` is preserved, and how `null` in bodies is handled.

A valid contract **does not make the producer emit messages on its own**. For generated producer tests to run properly, configure the trigger path and message-capture channel in the test environment.

## 6. Using YAML DSL to describe the same message

A team may choose **YAML DSL** instead of Groovy. Depending on your Spring Cloud Contract version, YAML messaging syntax and capabilities must be checked against documentation/tooling, as not every Groovy construct has a one-to-one YAML translation.

Example of **equivalent intent** in YAML DSL:

~~~yaml
description: Emit OrderCreated v1 for Billing Service
label: orderCreatedV1
input:
  triggeredBy: publishOrderCreated()
outputMessage:
  sentTo: orders.created
  headers:
    contentType: application/json
    eventType: OrderCreated
    schemaVersion: 1
  body:
    eventId: evt-00042
    orderId: ORD-1042
    amountMinor: 125000
    occurredAt: "2026-01-15T10:20:30Z"
    note: null
~~~

**This is an illustrative YAML messaging structure for discussion**, not a substitute for checking your Spring Cloud Contract version's parser. Before adopting it, verify the plugin's exact YAML schema, run test/stub generation, and inspect the actual body and headers. **Never treat “YAML parsed cleanly” as proof that the messaging contract was loaded and executed by the tooling.**

In practice, pick **one active DSL** for the same event. Never place both Groovy and YAML files for the same case under the plugin's scan path unless you want duplicate generated tests/stubs or drifting specifications.

## 7. Setting up the message-publishing path in the producer

Suppose the application uses **Spring Cloud Stream** with `StreamBridge` to emit events. The publishing path can be organized as:

~~~java
package com.acme.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderEventPublisher {
    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publishOrderCreated() {
        OrderCreated event = new OrderCreated(
            "evt-00042",
            "ORD-1042",
            125000L,
            java.time.Instant.parse("2026-01-15T10:20:30Z"),
            null
        );

        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventType", "OrderCreated")
            .setHeader("schemaVersion", 1)
            .build();

        boolean accepted =
            streamBridge.send("ordersCreated-out-0", message);
        if (!accepted) {
            throw new IllegalStateException("Cannot send OrderCreated");
        }
    }
}
~~~

Assume `OrderCreated` is the record from Section 2. `StreamBridge.send(...)` takes an **output binding name**, not always a raw broker topic name directly. Configuration might look like:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        ordersCreated-out-0:
          destination: orders.created
          content-type: application/json
~~~

In the contract, `sentTo('orders.created')` represents the message target; in code, `ordersCreated-out-0` is the `StreamBridge` binding. Configure the **message verifier adapter** and binder/test binder so the destination observed by generated tests **matches the destination described in the contract**. Do not assume matching strings alone mean every binder is wired up.

### 7.1. What does the base test class do?

Generated producer tests need a `publishOrderCreated()` method to trigger behavior. The base class may contain:

~~~java
@SpringBootTest
public abstract class MessageContractBase {
    @Autowired
    private OrderEventPublisher publisher;

    public void publishOrderCreated() {
        publisher.publishOrderCreated();
    }
}
~~~

This snippet only shows the **trigger path**. For Contract Verifier to actually capture the sent message, the project also needs **messaging test adapter, binder, or `MessageVerifier` configuration** supported by your Spring Cloud Contract version. Depending on transport/binder, that may use a test binder, fake channel, or broker testcontainer. **A base test with only a trigger method and no message-capture channel is not enough.**

If the producer emits messages asynchronously, tests must wait for **the exact emitted message** with a bounded timeout, rather than guessing with `Thread.sleep`. When multiple messages share a destination, distinguish them by `eventId`/header or fixture.

## 8. At which layer does the generated producer test inspect the payload?

Once configured properly, Contract Verifier can generate a meaningful test:

1. Call `publishOrderCreated()` on the base test.
2. Observe the message emitted to `orders.created` via the corresponding adapter.
3. Compare `headers` against the contract.
4. Compare the `body` presented to the test by the converter/adapter against the expected body.

However, **the level of assurance depends on the observation point**. If the test adapter receives `Message<OrderCreated>` before the binder converts it to JSON bytes, the test can **PASS** even though the real JSON serializer emits the wrong field name to the production broker. If the adapter observes post-serialization, it covers more of the wire format. **Always open the generated test, inspect message converter configuration, and trace the real send path to know where observation occurs.**

| Test level | Catches well | What it may miss |
| --- | --- | --- |
| Event object unit test | Field logic, Java types, domain mapping. | JSON bytes, transport headers, binder. |
| Generated messaging contract test at Spring Message abstraction | Defined destination, headers, and logical body. | Transport serializer if the test binder does not actually serialize. |
| Serialization test with real `ObjectMapper` | JSON field names, null/missing, timestamp formats, numeric types. | Kafka/AMQP header mapping or broker settings. |
| Integration test with test binder/broker | Data on transport, headers/codec, routing, and deserialization. | Operational conditions outside test scope: throughput, long retries, coordinated versions. |
| Consumer test with stubs | Consumer receives and handles sample messages. | Whether the real producer sent valid wire bytes if producer tests omit that check. |

**A strong test suite combines these layers**: do not expect Contract Verifier alone to prove every detail of Jackson, serializers, brokers, and deployment interfaces.

## 9. Verifying real serialization with Jackson

Example checking the JSON codec used by the producer. If `ObjectMapper` from the Spring Boot context includes Java Time support, a test can do:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.nio.charset.StandardCharsets;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderCreatedSerializationTest {
    @Autowired ObjectMapper objectMapper;

    @Test
    void serializesWireContractAsExpected() throws Exception {
        OrderCreated event = new OrderCreated(
            "evt-00042", "ORD-1042", 125000L,
            Instant.parse("2026-01-15T10:20:30Z"), null
        );

        byte[] bytes = objectMapper.writeValueAsBytes(event);
        JsonNode json = objectMapper.readTree(bytes);

        assertThat(json.get("eventId").asText()).isEqualTo("evt-00042");
        assertThat(json.get("orderId").asText()).isEqualTo("ORD-1042");
        assertThat(json.get("amountMinor").isIntegralNumber()).isTrue();
        assertThat(json.get("amountMinor").longValue()).isEqualTo(125000L);
        assertThat(json.get("occurredAt").asText())
            .isEqualTo("2026-01-15T10:20:30Z");
        assertThat(json.has("note")).isTrue();
        assertThat(json.get("note").isNull()).isTrue();

        String wireText = new String(bytes, StandardCharsets.UTF_8);
        assertThat(wireText).contains("\"orderId\"");
    }
}
~~~

This test verifies the **JSON payload** produced by an injected `ObjectMapper` in the test context. If the real app uses a **different serializer** for Spring Cloud Stream or Kafka, test that exact serializer: a Jackson test does not protect a producer using Avro/Protobuf or native encoding.

Specifically, the `json.has("note")` assertion is intentional. If `NON_NULL` is enabled and the field vanishes from JSON, the test **FAILS**, because this example contract requires an **explicit JSON null**. If your team's API omits `note` when null, align the contract and tests with that convention rather than forcing the example's choice.

### 9.1. Compare JSON structure rather than raw string literals

Two payloads:

~~~json
{"eventId":"evt-00042","orderId":"ORD-1042"}
~~~

~~~json
{"orderId":"ORD-1042","eventId":"evt-00042"}
~~~

have the **same JSON object meaning** despite differing key order. Unless a protocol requires canonical JSON, parse and compare field types and values instead of asserting byte-for-byte string equality. Conversely, for **digital signatures over bytes** or canonical-encoding protocols, exact byte layout is part of the requirement and must be tested accordingly.

## 10. Verifying deserialization on the consumer

Suppose Billing has an independent DTO without sharing classes with the producer:

~~~java
package com.acme.billing.events;

import java.time.Instant;

public record BillingOrderCreatedV1(
    String eventId,
    String orderId,
    long amountMinor,
    Instant occurredAt,
    String note
) {}
~~~

A consumer test can read a payload conforming to the agreed wire format:

~~~java
@Test
void readsOrderCreatedV1Json() throws Exception {
    String payload = """
        {
          "eventId":"evt-00042",
          "orderId":"ORD-1042",
          "amountMinor":125000,
          "occurredAt":"2026-01-15T10:20:30Z",
          "note":null
        }
        """;

    BillingOrderCreatedV1 decoded = objectMapper.readValue(
        payload, BillingOrderCreatedV1.class
    );

    assertThat(decoded.orderId()).isEqualTo("ORD-1042");
    assertThat(decoded.amountMinor()).isEqualTo(125000L);
    assertThat(decoded.occurredAt())
        .isEqualTo(Instant.parse("2026-01-15T10:20:30Z"));
    assertThat(decoded.note()).isNull();
}
~~~

**Important limitation:** on a DTO with only `String note`, `note()==null` **cannot distinguish** a payload containing `"note":null` from one **omitting `note`**. If the consumer must distinguish them, inspect `JsonNode`/`Map.containsKey` or use a DTO/deserializer that tracks field presence, and test both cases separately.

If the consumer uses a Spring Cloud Stream functional consumer like `Consumer<Message<BillingOrderCreatedV1>>`, the framework/binder may convert bytes into the DTO **before consumer code runs**. When checking compatibility, identify **which mapping/deserialization happens inside the binder** and run an integration test exercising that actual binder or adapter.

## 11. Stub Runner for messaging: simulating events, not HTTP

For HTTP, Stub Runner can start a WireMock server from the stubs artifact. For **message contracts**, emitting message stubs requires an **appropriate messaging integration**; it does not turn events into HTTP endpoints. A contract with `label 'orderCreatedV1'` can be used to trigger the sample message in a consumer test.

Conceptual JUnit test example on Billing:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingMessageContractTest {

    @Autowired StubTrigger stubTrigger;
    @Autowired BillingEventProbe billingProbe;

    @Test
    void handlesOrderCreated() {
        stubTrigger.trigger("orderCreatedV1");

        BillingOrderCreatedV1 received =
            billingProbe.awaitOrder("ORD-1042");
        assertThat(received.amountMinor()).isEqualTo(125000L);
    }
}
~~~

This is an **illustrative test skeleton**: `BillingEventProbe` and `awaitOrder(...)` must be implemented by the project with a bounded timeout and wired to the consumer's intake channel; Stub Runner/messaging imports and dependencies also require proper setup. `StubTrigger` is only meaningful once the plugin/binder connects event stubs to where the consumer listens—it does not start Kafka or RabbitMQ automatically or guarantee listener delivery on its own.

With `LOCAL`, the `stubs` artifact must be installed in local Maven by the producer; multi-runner CI typically publishes stubs and uses `REMOTE` with `repositoryRoot`/credentials. **Pin versions** so tests stay reproducible, instead of blindly pulling the latest snapshot without knowing which producer build published it.

**What the consumer test protects:** Billing's receive/deserialization/routing/handling code works with **the event sample in the contract**. **What it does not prove:** that the real Order Service serialized and sent valid bytes over the broker, or that the broker guarantees delivery/ordering/retries in all cases. Those require generated producer tests and corresponding integration tests.

## 12. When message contracts take broker input

Not every messaging contract starts from a `triggeredBy(...)` method. Sometimes a producer receives **an input message** and emits **an output message**. In Groovy DSL, this concept can be expressed as:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'invoiceRequestHandled'

    input {
        messageFrom('billing.invoice.request')
        messageBody(
            orderId: 'ORD-1042'
        )
        messageHeaders {
            header('contentType', 'application/json')
        }
    }

    outputMessage {
        sentTo('billing.invoice.created')
        headers {
            header('contentType', 'application/json')
        }
        body(
            orderId: 'ORD-1042',
            invoiceStatus: 'CREATED'
        )
    }
}
~~~

In this case, the test needs a **channel to feed the input message into the producer**, a converter reading the payload, a handler processing it, and a channel observing output—not merely a trigger method call. Support for `messageFrom`, `messageBody`, `messageHeaders`, and wiring to Spring Cloud Stream binders depends on version and adapter. Always **cross-check generated tests and real message sources** when applying this pattern.

For both input and output messages, clarify **raw payload** versus **post-deserialization payload** at each boundary. If a contract verifies an input message post-converter while the real upstream consumer sends JSON with the wrong field name, an overly high-level test can miss the bug. That is why testing real wire serialization/deserialization matters.

## 13. JSON, Avro, Protobuf: there is no single universal serializer

Spring Cloud Contract expresses exchange expectations, whereas **wire format** can be implemented with different technologies:

| Wire format | Characteristics | What else to check beyond the sample body |
| --- | --- | --- |
| **JSON** | Human-readable; converter may use Jackson; clear JSON number/string/null types. | Field naming, null/missing, timestamps, numbers, content type, charset. |
| **Avro** | Schema-driven binary, often with Schema Registry. | Schema ID/version, backward/forward compatibility, field defaults, decoding. |
| **Protobuf** | Binary per message definition; field numbers matter. | Field numbers, reserved fields, optional/presence, defaults, version. |
| **Text/raw bytes** | Plain text or custom byte stream per application format. | Encoding, delimiters, framing, checksums/signatures if used. |

If a producer uses an **Avro** Kafka serializer while generated contract tests only inspect a `Map` before serialization, they cannot catch a wrong Schema Registry ID. A **schema compatibility check** and an **integration test using the real serializer/deserializer** are better suited to protect that layer.

Not every schema check replaces a business contract: two schemas can be syntactically compatible while changing `amountMinor`'s meaning from “VND” to “cents”, causing Billing to miscalculate money even though parsing succeeds.

## 14. Managing versioning and compatibility when message shapes change

Changes that look like minor serializer tweaks can directly break consumers:

| Change | Risk | Protection strategy |
| --- | --- | --- |
| `orderId` → `order_id` | Consumer reading `orderId` fails to map it. | Lock naming strategy or version the event. |
| `amountMinor` from number to string | DTO/validation or arithmetic fails. | Test wire JSON and consumer deserializer. |
| `occurredAt` ISO string → epoch number | Old time parser is incompatible. | Keep old schema or plan versioning/migration. |
| Enabling `NON_NULL` drops `note:null` | Consumers distinguishing null vs. missing are affected. | Dedicated contracts/tests for presence and null. |
| `eventType` moved from header to body | Consumers routing by header break. | Align and test headers over real transport. |
| Renaming destination/topic | Listeners miss events despite valid payload. | Messaging contract + routing integration test. |
| Enum `CREATED` → `created` | Case-sensitive consumers may fail. | Protect enum literals in the contract. |
| Adding an optional field | Compatible only if consumers ignore unknown fields. | Check unknown-fields policy; test older consumers. |
| Removing a field, changing meaning, or narrowing domain | Can break active consumers. | Release new version, keep old contracts while needed, test consumer matrix. |

**Compatibility must be evaluated in the direction producer emits → consumer receives.** For instance, a consumer running Jackson with `FAIL_ON_UNKNOWN_PROPERTIES` may reject a new field even if a JSON schema treats it as optional. Never stop at checking that the producer sends “valid” JSON without checking how older consumers deserialize it.

When multiple event versions coexist, teams may use type names like `OrderCreatedV1`, a `schemaVersion` header, versioned topics, or a schema registry; what matters is that **routing and decoding rules are documented, tested, and lifecycle-managed**.

## 15. A test matrix for pre- and post-serialization

In CI, verify the following checkpoints:

| Test | Input | Primary assertion | What bug does it catch? |
| --- | --- | --- | --- |
| **Domain event test** | Order-creation command | `OrderCreated` object has right ID/amount/time. | Business → event mapping bug. |
| **Messaging contract producer test** | `triggeredBy` or message input | Output destination, headers, and payload match contract. | Producer changed event behavior observable via adapter. |
| **JSON wire test** | Producer object | JSON bytes, fields/types/nulls/timestamps match. | Wrong serializer/Jackson config. |
| **Transport integration test** | Publish via test binder/broker | Consumer receives right bytes/headers/destination. | Wrong header mapping, codec, route, or native encoding. |
| **Consumer deserializer test** | Payload per contract version | DTO maps cleanly, malformed data handled. | Consumer fails to parse event. |
| **Stub Runner consumer test** | Trigger labeled event | Consumer receives, processes, and creates expected side effects. | Client/listener logic diverges from contract. |
| **Schema compatibility test** (if used) | Old and new schemas | Satisfies chosen compatibility policy. | Avro/Protobuf/schema breaking changes. |

CI flow:

~~~mermaid
flowchart TD
    A["Producer or contract change"] --> B["Review event schema + metadata"]
    B --> C["Verifier generates producer message tests"]
    C --> D["Run body/header/destination tests"]
    D --> E["Test serializer and transport"]
    E --> F{"All producer checks pass?"}
    F -->|No| G["Block publishing stubs and event version"]
    F -->|Yes| H["Publish versioned stubs"]
    H --> I["Consumer CI: Stub Runner + deserialization"]
    I --> J["Verify compatibility with older consumers"]
~~~

**Do not check only JSON strings in unit tests while skipping generated producer tests.** Conversely, **do not check only message objects through a test binder** while ignoring the production serializer. Both test groups complement each other, protecting **event semantics** as well as **wire representation**.

## 16. Common failures and how to investigate

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Producer test passes, Billing fails to parse message. | Test converter/serializer differs from broker serializer; wire field changed. | Capture actual payload bytes + headers, run consumer deserializer. |
| `occurredAt` becomes a number instead of a string. | Jackson date/time config or different serializer. | Check `ObjectMapper`/Java Time module, timestamp settings, and payload bytes. |
| `note:null` disappears. | `NON_NULL` or converter strips nulls. | Test `JsonNode.has("note")` and `isNull()`. |
| Monetary amount is wrong after decoding. | Double precision, scale, or currency unit mismatch. | Compare JSON types and integer minor units/BigDecimal per policy. |
| Consumer receives empty `eventType` header. | Header filtered/renamed by binder or not published. | Inspect pre-send message and metadata on a real broker. |
| Consumer receives a JSON string wrapped in extra quotes. | Double serialization: JSON string encoded a second time. | Inspect raw bytes, payload type before converter, and content type. |
| No generated producer messaging tests appear. | Contract not loaded by plugin or wrong test framework/messaging adapter. | Inspect generated test sources, test reports, Contract Verifier config. |
| Test reports no message at destination. | Wrong `sentTo`, output binding differs from broker destination, subscriber not ready. | Check `spring.cloud.stream.bindings`, adapter, and real channel. |
| Stub trigger runs yet listener receives nothing. | Messaging stub adapter/binder unconfigured or wrong label. | Check `StubTrigger`, label name, destination, test binder, and subscriber. |
| Consumer test passes even though producer fails to publish. | Stub simulates valid message while real producer lacked verification. | Block publishing when producer tests fail; add transport integration tests. |
| CI flakes between pass and fail. | Async message delayed, queue holds old messages, unclear timeouts. | Isolate topics/queues, use event IDs, await with bounded deadlines. |

When debugging, trace **producer object → Spring Message → serializer → broker bytes/metadata → deserializer → consumer object**. Record exact payloads and headers at every boundary instead of logging Java `toString()` and assuming wire messages match.

## 17. Practice exercise: catching bugs between producer and consumer

On a Spring Boot/Spring Cloud Stream project with Spring Cloud Contract Verifier and a consumer using Stub Runner:

1. **Define event `OrderCreatedV1`** with `eventId`, `orderId`, `amountMinor`, `occurredAt`, `note`; document JSON types, currency unit meaning, and null rules.
2. **Create a Groovy message contract** with `label=orderCreatedV1`, `triggeredBy`, `sentTo=orders.created`, headers, and body as in Section 5; keep only one official DSL.
3. **Implement the publishing path** with `StreamBridge`, configuring the output binding to point to the destination used by the contract.
4. **Create the base test and messaging adapter** so generated producer tests can trigger publishing and observe the right message; confirm tests are generated, executed, and PASS.
5. **Write a JSON serialization test** using the producer's real `ObjectMapper`; verify `note` appears as JSON `null`, `occurredAt` as an ISO string, and `amountMinor` as an integer.
6. **Introduce an intentional bug**: enable `NON_NULL` so `note` disappears. Verify the wire-format test FAILS, and explain why the generated message test might still PASS if it observes objects before serialization.
7. **Try changing the naming strategy** so `orderId` becomes `order_id`. Observe failures in the wire JSON test and/or consumer deserializer, then revert.
8. **Run a transport integration test** with an appropriate binder/broker; verify `eventType` and `schemaVersion` headers actually reach the receiving side.
9. **Package/install or publish stubs** after producer verification passes. Use Stub Runner to trigger the label and confirm the real consumer handles `ORD-1042`.
10. **Simulate a schema upgrade**: add an optional field, remove a required field, or change `amountMinor` from number to string. Assess compatibility with older consumers; release only with a migration plan and matching tests.

**Completion criteria:** learners can identify **which values exist before serialization**, **which JSON bytes/headers actually cross the transport**, **which DTO the consumer receives after deserialization**, and **which test layer catches failures when the three representations diverge**.

## 18. Self-check questions

1. Why does having `Message<OrderCreated>` not mean the broker received a JSON object?
2. How does a `contentType` header differ from a JSON `contentType` field inside the body?
3. If the producer's `ObjectMapper` omits nulls, what can `{"note":null}` turn into? When is that a breaking change?
4. Does a generated producer test comparing Java-object payloads catch every Kafka/AMQP serialization bug?
5. Why can a consumer with its own DTO fail to map `order_id` when the earlier contract specified `orderId`?
6. What category of risks does using `long amountMinor` instead of `double amount` reduce? What else must be specified about currency units?
7. What configuration connects `sentTo('orders.created')` and `streamBridge.send("ordersCreated-out-0", ...)`?
8. Does Stub Runner with a message contract automatically start a production broker and run the real producer?
9. Why does a passing consumer stub test not prove the producer publishes valid wire bytes?
10. When switching a timestamp from an ISO string to an epoch number, why can producer and consumer still be incompatible even though both represent the same instant?

**Key takeaway:** **The object before serialization, the payload after serialization, and the object after deserialization are not automatically identical.** Spring Cloud Contract messaging contracts must accurately express the payload, headers, and destination consumers depend on; generated producer tests verify the configured publishing path, while **serialization and transport integration tests** protect real wire bytes and metadata. Consumers use Stub Runner to test event handling independently, and CI coordinates these verification layers before releasing new event versions—preventing serializer changes from silently becoming breaking changes for active consumers.
