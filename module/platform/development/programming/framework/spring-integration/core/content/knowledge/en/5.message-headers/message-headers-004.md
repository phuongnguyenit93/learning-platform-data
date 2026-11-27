# contentType

## Lesson objectives

In the **Message headers** chapter of the **SPRING_INTEGRATION_CORE** module, `contentType` helps components agree on how to interpret the data a message is carrying. As a flow passes through gateways, channels, transformers, and adapters, this information must match the payload's representation at each boundary.

After this lesson, you can:

- Distinguish between the payload's Java type, its content type, and data conversion operations.
- Read, set, and update `MessageHeaders.CONTENT_TYPE` properly.
- Design a step that converts objects to JSON using Java DSL without accidentally retaining a stale header.
- Handle missing, malformed, or unsupported headers.
- Write tests that verify both the data content and its metadata.

The examples below use Java 17, Spring Integration 6.5.x, Spring Framework 6.2.x, Jackson 2, and JUnit Jupiter 5. These serve as API baselines for the examples; specific dependency versions should follow your application's BOM.

## 1. What does `contentType` describe?

A message can be visualized as follows:

```text
Message
├── payload: the data being transported
└── headers
    └── contentType: describes the content type of the data
```

Spring provides the `MessageHeaders.CONTENT_TYPE` constant, corresponding to the `contentType` key. Use the constant to avoid typos. With standard messages created via `MessageBuilder`, update headers by using a builder to create the resulting message; calling `message.getHeaders().put(...)` directly will throw `UnsupportedOperationException`. See [MessageHeaders in Spring Framework](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageHeaders.html).

Some common values:

| Value | Meaning in the data contract |
| --- | --- |
| `application/json` | Data formatted in JSON syntax |
| `application/xml` | XML document |
| `text/plain;charset=UTF-8` | Plain text; when represented as bytes, use UTF-8 |
| `text/csv;charset=UTF-8` | CSV text; column conventions and delimiters need additional agreement |
| `application/octet-stream` | Generic binary data, without a specialized structure description |

A media type has a type and a subtype, such as `application` and `json`; parameters may follow. `MimeType` supports representing and parsing these parts. See [MimeType API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/util/MimeType.html).

There are three distinct questions to answer:

| Question | Example |
| --- | --- |
| What Java object is the payload currently? | `String`, `byte[]`, `Map`, or `Order` |
| In what format is the data represented? | JSON, XML, CSV, or plain text |
| Which component performs the conversion? | A JSON transformer or configured message converter |

A `String` can contain JSON, XML, or a plain sentence. A `byte[]` can hold UTF-8-encoded JSON or image data. Therefore, inspecting `payload.getClass()` alone is not enough to determine the format.

Conversely, `contentType=application/json` does not prove the payload is valid JSON, does not reveal the business schema, and does not specify the target class for deserialization. The receiver still needs an appropriate parser, target type, and data validation.

## 2. Setting the header does not automatically convert the payload

Consider the following message:

```java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Map<String, Object> order = Map.of(
        "orderId", "DH-004",
        "quantity", 2
);

Message<Map<String, Object>> message = MessageBuilder
        .withPayload(order)
        .setHeader(MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON)
        .build();

boolean stillAMap = message.getPayload() instanceof Map; // true
```

The builder only attaches metadata; it does not call Jackson to produce a JSON string. Sending this message through a `DirectChannel` does not automatically trigger a JSON converter either.

In a specific application, a converter or adapter might accept a `Map` alongside a JSON header and perform serialization. That depends on the configured component. If the consumer's contract requires JSON in text form, an explicit step to produce JSON text is needed.

The design rule is: **the component that changes the data representation must establish metadata matching the output**.

For example, a flow that receives CSV text, parses it into an object, and outputs JSON requires three decisions:

1. Which parser understands the incoming CSV?
2. What business structure does the internal object have?
3. Which step generates JSON and sets `application/json` on the outbound message?

Changing a CSV label to JSON before running the parser obscures the original meaning of the data.

## 3. Reading the header as a `MimeType`

In practice, the header may be a `String` like `"application/json"` or a `MimeType` object. `DefaultContentTypeResolver` supports both forms. When the header is absent and no default value is configured, the resolver returns `null`. See [DefaultContentTypeResolver](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/converter/DefaultContentTypeResolver.html).

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.DefaultContentTypeResolver;
import org.springframework.util.MimeType;

public final class ContentTypes {

    private static final DefaultContentTypeResolver RESOLVER =
            new DefaultContentTypeResolver();

    private ContentTypes() {
    }

    public static MimeType resolve(Message<?> message) {
        return RESOLVER.resolve(message.getHeaders());
    }

    public static boolean isApplicationJson(Message<?> message) {
        MimeType type = resolve(message);
        return type != null
                && "application".equalsIgnoreCase(type.getType())
                && "json".equalsIgnoreCase(type.getSubtype());
    }
}
```

The `isApplicationJson` method expresses a concrete policy: it accepts `application/json`, even with additional parameters, without automatically broadening to every media type ending in `+json`. If the business domain accepts `application/vnd.example.order+json`, add that case explicitly along with corresponding tests.

Avoid comparing the entire header with:

```java
"application/json".equals(
        message.getHeaders().get("contentType")
);
```

This comparison misses `MimeType` headers and strings with parameters. Using the resolver and then checking type and subtype accurately expresses the intended rule.

A syntactically invalid header or wrong object type can cause resolution to fail with an exception. At untrusted entry points, distinguish three situations: missing header, invalid header, and valid media type outside the supported list.

Do not default to JSON merely to suppress missing-header errors. Only apply a default if the input contract specifies that any message without the header has a well-defined format.

## 4. Creating a new message when updating `contentType`

The two operations below have different meanings:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

// Only appropriate when the input is known to lack a label while the payload is actually JSON.
Message<?> withDefault = MessageBuilder.fromMessage(input)
        .setHeaderIfAbsent(MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON)
        .build();

// Appropriate when the preceding step just produced a new JSON representation.
Message<?> withCurrentType = MessageBuilder.fromMessage(input)
        .setHeader(MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON)
        .build();
```

Here `input` is an existing message in the flow. `setHeaderIfAbsent` keeps any existing value; `setHeader` actively replaces it. The choice depends on whether you are filling in missing information or describing a newly created representation.

Practical examples:

| Situation | How to handle |
| --- | --- |
| Input already contains valid JSON but lacks a label per contract | May add a default header |
| Payload was just converted from XML to JSON | Overwrite with `application/json` |
| Payload was just converted from JSON to report text | Overwrite with `text/plain`, with a charset convention at byte boundaries |
| Payload has become an internal domain object | Decide clearly whether the header still describes the source representation or should be removed per internal contract |

If you need to keep the content type from ingestion for tracing, store it in a separate header such as `sourceContentType` before changing the representation. Never use the same header to mean both "source format" and "output format" at the same time.

## 5. A common pitfall with `ObjectToJsonTransformer`

`ObjectToJsonTransformer` converts a payload into a JSON representation. By default, the transformer sets `application/json` when the input message has no `contentType`; an existing header may be preserved. See [JSON Transformers](https://docs.spring.io/spring-integration/reference/6.5/transformer.html#json-transformers).

Consider this scenario:

```text
Input:
  payload     = Map containing order data
  contentType = text/plain

After the JSON creation step without proactively updating the label:
  payload     = JSON string
  contentType = text/plain   ← metadata no longer matches
```

In this example, `text/plain` is stale metadata carried along with the object from earlier processing steps. The output may contain valid JSON, yet a consumer picks a plain-text processor because it sees the old label.

For an endpoint that always produces standard JSON, configure:

```java
transformer.setContentType("application/json");
```

This setter establishes the output content type even when the input has a different value. The API and constructors for choosing result types are documented at [ObjectToJsonTransformer](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/json/ObjectToJsonTransformer.html).

This setting must accompany actual JSON generation. Do not slap a JSON label onto an arbitrary payload and treat that as a serialization step.

## 6. Complete Java DSL example

Problem statement: a system receives an order object and produces JSON to hand off to an outbound sender component. The internal flow ends at a `QueueChannel` so the output can be observed and tested without an HTTP server or broker.

```mermaid
flowchart LR
    A["Order object"] --> B["orders.input: DirectChannel"]
    B --> C["ObjectToJsonTransformer"]
    C --> D["JSON String + application/json"]
    D --> E["orders.output: QueueChannel"]
    E --> F["Outbound sender component"]
```

The application needs `spring-integration-core`, `jackson-databind`, and compatible Spring dependencies; tests need `junit-jupiter`. Spring dependencies should be managed by a BOM or Spring Boot. With the plain Spring configuration below, `@EnableIntegration` registers the Integration infrastructure.

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.json.ObjectToJsonTransformer;
import org.springframework.integration.support.json.Jackson2JsonObjectMapper;

@Configuration
@EnableIntegration
public class ContentTypeFlowConfig {

    @Bean(name = "orders.input")
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.output")
    public QueueChannel ordersOutput() {
        return new QueueChannel();
    }

    @Bean
    public ObjectMapper orderObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    public ObjectToJsonTransformer orderJsonTransformer(
            ObjectMapper orderObjectMapper) {

        ObjectToJsonTransformer transformer = new ObjectToJsonTransformer(
                new Jackson2JsonObjectMapper(orderObjectMapper),
                ObjectToJsonTransformer.ResultType.STRING
        );

        transformer.setContentType("application/json");
        return transformer;
    }

    @Bean
    public IntegrationFlow orderJsonFlow(
            ObjectToJsonTransformer orderJsonTransformer) {

        return IntegrationFlow.from("orders.input")
                .transform(orderJsonTransformer)
                .channel("orders.output")
                .get();
    }
}
```

Java DSL provides `.transform(...)` to place a transformer into the flow. The example uses a dedicated bean so the header policy sits right next to the JSON generation configuration. Reference [Transformers in Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-transformers.html).

Under this flow's contract:

- The input is a Java object serializable by Jackson.
- The output is a `String` containing JSON, with the `application/json` header.
- A business header such as `traceId` should continue traveling with the message for tracing.
- The outbound adapter sending data afterward must be configured appropriately for a payload that is already JSON.

In particular, if the input is already a JSON string, serializing that string can produce a JSON string containing an escaped string instead of preserving a JSON object. Therefore, do not mechanically route every JSON-labeled payload through an object-to-JSON transformer. Determine whether the payload is an object to serialize or an already-complete JSON document.

A messaging gateway can serve as the entry point to this flow, but the gateway and channel do not replace the transformer's serialization responsibility.

## 7. Testing payload and header together

A test that only checks `contentType` can miss a non-JSON payload. A test that only parses JSON can miss a leftover `text/plain` label.

Place the test class in the same package as `ContentTypeFlowConfig`:

```java
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.DefaultContentTypeResolver;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import static org.junit.jupiter.api.Assertions.*;

class ContentTypeFlowTest {

    @Test
    void writesJsonAndReplacesStaleContentType() throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ContentTypeFlowConfig.class)) {

            MessageChannel input =
                    context.getBean("orders.input", MessageChannel.class);
            QueueChannel output =
                    context.getBean("orders.output", QueueChannel.class);
            ObjectMapper mapper = context.getBean(ObjectMapper.class);

            Message<Map<String, Object>> request = MessageBuilder
                    .withPayload(Map.<String, Object>of(
                            "orderId", "DH-004",
                            "customer", "Nguyễn Ánh",
                            "quantity", 2))
                    .setHeader(MessageHeaders.CONTENT_TYPE,
                            MimeTypeUtils.TEXT_PLAIN)
                    .setHeader("traceId", "trace-004")
                    .build();

            assertTrue(input.send(request));

            Message<?> result = output.receive(1_000);
            assertNotNull(result);

            String json = assertInstanceOf(String.class, result.getPayload());
            JsonNode document = mapper.readTree(json);

            assertEquals("DH-004", document.path("orderId").asText());
            assertEquals("Nguyễn Ánh", document.path("customer").asText());
            assertEquals(2, document.path("quantity").asInt());

            MimeType type = new DefaultContentTypeResolver()
                    .resolve(result.getHeaders());

            assertEquals(MimeTypeUtils.APPLICATION_JSON, type);
            assertEquals("trace-004", result.getHeaders().get("traceId"));
        }
    }

    @Test
    void resolvesStringAndMimeTypeHeaders() {
        DefaultContentTypeResolver resolver =
                new DefaultContentTypeResolver();

        Message<String> stringHeader = MessageBuilder.withPayload("{}")
                .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
                .build();

        Message<String> mimeTypeHeader = MessageBuilder.withPayload("{}")
                .setHeader(MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .build();

        assertEquals(resolver.resolve(stringHeader.getHeaders()),
                resolver.resolve(mimeTypeHeader.getHeaders()));

        Message<String> missingHeader = MessageBuilder.withPayload("{}")
                .build();

        assertNull(resolver.resolve(missingHeader.getHeaders()));
    }
}
```

The first test proves four observable properties: the output is a parseable JSON string, business data is preserved, the stale label is replaced, and `traceId` remains intact. It avoids comparing the entire raw JSON string because property ordering is not part of this contract.

When applying this to a real project, add test cases matching actual inputs:

| Test case | What to prove |
| --- | --- |
| Valid object, no header yet | Produces JSON output with the right label |
| Input header is currently XML or plain text | JSON generation step updates the label |
| Malformed JSON string in a JSON-receiving flow | Parser rejects the data; a valid header does not make invalid data valid |
| Media type with parameters | Classifier applies the right policy |
| Vietnamese characters at byte boundaries | Bytes are encoded and decoded with the same charset |
| Payload is already a JSON string | Does not accidentally serialize an extra layer |

The test snippets serve as practice material for learners; running them requires the application's dependency environment.

## 8. `charset`, `String`, and `byte[]`

A Java `String` holds characters; charset issues arise when converting between characters and bytes. A `charset=UTF-8` header does not retroactively fix a byte array that was already created with a different encoding.

Example with plain text:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeType;

String text = "Đơn hàng DH-004 đã được tiếp nhận";
byte[] body = text.getBytes(StandardCharsets.UTF_8);

Message<byte[]> message = MessageBuilder.withPayload(body)
        .setHeader(MessageHeaders.CONTENT_TYPE,
                new MimeType("text", "plain", StandardCharsets.UTF_8))
        .build();

String decoded = new String(message.getPayload(), StandardCharsets.UTF_8);
```

Here the bytes and the header agree because the encoding operation explicitly chose UTF-8. If an adapter will perform the encoding step, configure and test that adapter rather than assuming all components honor the charset parameter the same way.

For outbound JSON flows, agree on both the format and how bytes are transmitted. Testing with Vietnamese data helps catch cases where JSON is structurally valid yet text diacritics are corrupted.

## 9. Across HTTP, broker, and converter boundaries

In internal messages, the key is `contentType`. In HTTP, the corresponding protocol field is named `Content-Type`. Do not create an extra internal header named `"Content-Type"` and expect every adapter to treat it as `MessageHeaders.CONTENT_TYPE`.

Spring Integration provides header mappers for HTTP. Standard HTTP headers are mapped by default configuration; when customizing header lists, verify carefully because new configuration can alter which headers are mapped. See [HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/6.5/http/header-mapping.html).

At protocol boundaries, confirm three things:

1. **Payload:** Is the sending/receiving component working with objects, strings, or bytes?
2. **Converter:** Which component serializes or deserializes, and to which target type?
3. **Header mapper:** How is internal metadata mapped to protocol attributes?

For example, if the flow already produced a JSON string, the outbound converter must treat it as already-serialized content. If the converter still treats that string as an object to serialize, the receiver may get an extra layer of quotes and escape characters.

HTTP `Accept` describes the content type desired in the response; `Content-Type` describes the body being sent. Configuring `Accept: application/json` does not substitute for declaring and producing a proper JSON request body.

With brokers, protocol property names, header-type preservation, and converter selection depend on the adapter and transport library. Test at the real boundary when transitioning from an internal flow to an external protocol.

## 10. Using `contentType` for filtering and routing

In a flow accepting multiple formats, you can use the media type to pick the JSON or XML branch. This is an input-classification step; the branch's parser must still verify the data.

```text
Input message
  → read and parse contentType
  → missing / malformed / unsupported: reject branch
  → application/json: JSON parser
  → application/xml: XML parser
  → validated domain object
```

This is a recommended design for a system needing a strict input contract. For a source providing only a single format with a clear default convention, the missing-header policy may differ.

When using a router or filter:

- Media-type parsing failures should be handled as metadata errors.
- A valid media type with an invalid body should be handled as data-parsing errors.
- A syntactically valid body missing business fields should be handled at the validation step.
- Rejected messages should carry a reason code and tracing info so operations can distinguish error groups.

A filter returning `false` does not automatically create a complete error record. If you need to store dropped messages, configure a discard branch; if you need to report failure to the caller, choose an appropriate error mechanism.

In a synchronous flow over `DirectChannel`, endpoint errors can usually propagate back to the sender. When an executor or poller is involved, errors occur on another execution thread; configure the endpoint's error-reporting mechanism and monitor the appropriate error flow. Do not assume merely setting an `errorChannel` header causes every error to be sent there automatically.

## 11. Diagnosing common errors

| Symptom | Cause to investigate | Fix |
| --- | --- | --- |
| Header says JSON but payload is still a `Map` | Only added the header without serializing | Place a transformer or converter at the boundary requiring JSON |
| Payload is JSON but header is still `text/plain` | Old label was retained after conversion | Configure the output content type explicitly |
| Validator rejects JSON with parameters | Comparing the entire header string | Parse into `MimeType` and apply policy by parts |
| Type-casting error on header | Assuming all values are `String` or all are `MimeType` | Use the resolver and define accepted types |
| Vietnamese characters have corrupted diacritics | Bytes encoded and decoded with different charsets | Inspect character ↔ byte conversion steps |
| Receiver gets JSON with many escape characters | Already-serialized payload was serialized again | Designate a single step responsible for serialization |
| HTTP does not receive the right content type | Mapper, converter, or body config misaligned | Inspect the real request and reconcile all three parts at the boundary |

When observing the system, log the payload class, `contentType` value, active endpoint, and trace ID. Those facts are usually enough to isolate whether a label mismatch occurred before or after a transformer.

## 12. Practice exercises

Using the configuration in section 6, carry out these steps:

1. Send a `Map` with an order ID, quantity, and a customer name in Vietnamese; leave `contentType` unset.
2. Verify the output is parseable JSON labeled `application/json`.
3. Send the same data with an input header of `text/plain`; confirm the output label is still correct.
4. Temporarily remove `setContentType("application/json")`, rerun the stale-label case, and observe the difference.
5. Restore the configuration, add `traceId`, and verify that business metadata still travels with the result.
6. Design an additional entry point receiving text-based JSON with policies for missing headers and malformed JSON.

The expected takeaway is: `contentType` describes the content contract; the transformer or converter produces the matching representation; tests must verify that both are correct together at the handoff boundary.
