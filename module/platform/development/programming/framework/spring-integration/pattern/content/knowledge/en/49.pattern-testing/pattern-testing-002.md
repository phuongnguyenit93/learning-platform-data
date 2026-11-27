# Testing Payload and Headers in Spring Integration

## 1. Why Must Payload and Headers Be Tested Together?

In **Enterprise Integration Patterns (EIP)**, a message is passed between components without forcing them to depend directly on one another. In **Spring Integration**, business content lives in the **payload**, while **headers** provide context for routing, tracing, grouping, and replying. A Transformer may return the right payload yet drop the tenant ID; a Router may send to the wrong branch because it misreads a header's data type; an Aggregator may merge two orders by mistake because of a wrong correlation ID.

This lesson belongs to the **Pattern Testing** chapter of the **SPRING_INTEGRATION_PATTERN** module. The objective is to verify precisely what flows through a Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, and error channel, while maintaining a loosely coupled, extensible, and traceable message flow.

After this lesson, you will be able to:

1. Build small messages containing only the payload and headers truly required by the scenario.
2. Verify the value, **type**, structure, and immutability of the payload.
3. Distinguish business headers from framework-managed headers.
4. Detect missing, erroneously added, improperly overwritten, or absent headers where presence is required.
5. Verify correlation, sequence, routing, error handling, and retry across processing steps.
6. Write stable assertions that avoid depending on IDs, timestamps, and execution timing not guaranteed by the system.

**Principle:** A good test describes *the contract of a message at a boundary*, including its payload, headers, and emission conditions. Do not assert every header merely because it happened to be present in a single run.

## 2. Structure of a Message

In Spring Messaging, the central type is \`org.springframework.messaging.Message<T>\`:

~~~text
Message<T>
├── payload: T
│   └── "  SKU-42  "                (business data)
└── headers: MessageHeaders
    ├── id: UUID                   (managed by framework)
    ├── timestamp: long            (managed by framework)
    ├── tenantId: "shop-a"         (business)
    ├── route: "priority"          (business / routing)
    ├── correlationId: "order-42"  (links elements in the same group)
    ├── sequenceNumber: 1          (member position within the group)
    ├── sequenceSize: 2            (expected member count)
    ├── replyChannel: ...          (reply destination, when needed)
    └── errorChannel: ...          (error destination, when needed)
~~~

Example of building a minimal message with \`MessageBuilder\`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> request = MessageBuilder.withPayload("  SKU-42  ")
        .setHeader("tenantId", "shop-a")
        .setHeader("route", "priority")
        .build();
~~~

\`MessageBuilder\` automatically generates system headers such as \`id\` and \`timestamp\` according to framework rules. These values are useful for diagnostics, but usually should **not** be hardcoded in business tests.

### Contract Classification

| Message Part | Example | What the Test Must Assert | Common Mistakes |
| --- | --- | --- | --- |
| Payload | \`"SKU-42"\` | Exact value after normalization | Only checking non-\`null\`, missing bad data |
| Payload type | \`OrderDto\`, \`List<String>\` | Exact type and structure expected by the next step | Mistaking a JSON string for a DTO |
| Business header | \`tenantId="shop-a"\` | Present, right type, and right value | Header lost during transform or gateway |
| Control header | \`route="priority"\` | Router uses the exact value | Case mismatch or missing branch mapping |
| Correlation | \`correlationId="order-42"\` | Elements of the same group share the same key | Merging messages from two different orders |
| Sequence | \`sequenceNumber=1\`, \`sequenceSize=2\` | Correct metadata per split/aggregate strategy | Group releasing too early or never releasing |
| Framework header | \`id\`, \`timestamp\` | Present and of expected type if needed | Test comparing fixed UUIDs or timestamps |
| Reply/error header | \`replyChannel\`, \`errorChannel\` | Message reaches the right channel as configured | Assuming synchronous errors are automatically sent to the error channel |

## 3. Designing Small Yet Powerful Test Datasets

You do not need an order object with dozens of fields just to test a whitespace-trimming Transformer. Start with the smallest value that makes the expected behavior **distinguishable** from buggy behavior.

| Contract | Minimal Message | What Cases to Add to Catch Bugs? |
| --- | --- | --- |
| String normalization | Payload \`"  A  "\` | \`"A"\`, whitespace-only string, and Unicode characters |
| Type validation | Payload of one \`OrderDto\` | Blank required field, invalid value |
| Preserve tenant | Payload \`"A"\`, \`tenantId="t1"\` | Missing \`tenantId\`; wrong value type |
| Header enrichment | Payload \`"A"\`, no \`stage\` | Existing \`stage\`: overwritten or preserved? |
| Header-based router | Payload \`"A"\`, \`route="priority"\` | \`route="normal"\`, missing \`route\` |
| Splitter | Payload \`["A","B"]\` | Empty list; verify correlation/sequence |
| Aggregator | Two messages sharing \`correlationId\`, sequence numbers 1 and 2 | Two interleaved groups, missing second element |
| Retry | Payload \`"A"\`, \`requestId="r1"\` | Handler fails transiently then succeeds, request ID unchanged |
| Error handling | One message causing an error, with source info | Exception and failed message recorded per configuration |

For instance, when testing \`tenantId\`, sending payload \`"A"\` with a single header is sufficient. Only add \`correlationId\`, \`route\`, or \`sequenceSize\` if the flow actually uses them. Small test fixtures clarify the source of a failure and avoid coupling to oversized sample data.

## 4. Unit Testing: Payload, Data Types, and Headers

The examples below use **Java 17**, **JUnit 5**, and **AssertJ**. You can run unit tests with \`spring-boot-starter-test\` and compatible Spring Messaging/Integration dependencies. The goal of this section is to test messages directly without creating an \`ApplicationContext\`.

~~~java
package example;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class PayloadHeaderUnitTest {

    @Test
    void payload_has_expected_value_and_type() {
        Message<String> message = MessageBuilder
                .withPayload("  SKU-42  ")
                .build();

        assertThat(message.getPayload()).isInstanceOf(String.class);
        assertThat(message.getPayload()).isEqualTo("  SKU-42  ");
    }

    @Test
    void business_headers_keep_values_and_types() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .setHeader("tenantId", "shop-a")
                .setHeader("attempt", 2)
                .setHeader("retryable", true)
                .build();

        assertThat(message.getHeaders().get("tenantId"))
                .isEqualTo("shop-a");
        assertThat(message.getHeaders().get("attempt"))
                .isInstanceOf(Integer.class)
                .isEqualTo(2);
        assertThat(message.getHeaders().get("retryable"))
                .isEqualTo(true);

        assertThat(message.getHeaders())
                .containsKeys(MessageHeaders.ID, MessageHeaders.TIMESTAMP);
    }

    @Test
    void absent_header_is_distinguished_from_present_header() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .build();

        assertThat(message.getHeaders()).doesNotContainKey("tenantId");
        assertThat(message.getHeaders().get("tenantId")).isNull();
    }

    @Test
    void setting_header_if_absent_does_not_override_existing_value() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .setHeader("tenantId", "shop-a")
                .setHeaderIfAbsent("tenantId", "fallback")
                .build();

        assertThat(message.getHeaders().get("tenantId"))
                .isEqualTo("shop-a");
    }

    @Test
    void message_headers_are_read_only() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .setHeader("tenantId", "shop-a")
                .build();

        assertThatThrownBy(() ->
                message.getHeaders().put("tenantId", "shop-b"))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

These tests distinguish three critical cases:

- **A header with the right value but wrong type** is still a bug. For example, \`attempt="2"\` (String) differs from \`attempt=2\` (Integer). A component reading an integer might fail to handle a string.
- **An absent header** differs from a header with a valid but empty value. With \`MessageBuilder.setHeader("key", null)\`, the usual behavior is removing the header; therefore, assert \`containsKey\` when presence is required by the contract.
- **MessageHeaders cannot be modified directly**. However, the payload can point to a mutable object or collection; header immutability does **not** guarantee deep immutability of the payload. Use \`record\`, immutable DTOs, or defensive copies if parallel flows can share the payload.

### Testing Object Payloads

In real systems, payloads are often DTOs. Tests should verify business fields rather than \`toString()\`:

~~~java
record OrderLine(String sku, int quantity) {}

@Test
void structured_payload_keeps_business_fields() {
    Message<OrderLine> message = MessageBuilder
            .withPayload(new OrderLine("SKU-42", 3))
            .build();

    assertThat(message.getPayload().sku()).isEqualTo("SKU-42");
    assertThat(message.getPayload().quantity()).isEqualTo(3);
}
~~~

Spring Messaging does not allow a Java \`null\` payload in a regular message built with \`MessageBuilder.withPayload(null)\`. If business logic needs to represent "no value", define an explicit contract: an Optional value at the application boundary, a status-representing DTO, an end-of-stream message, or an appropriate empty-handling mechanism. Do not construct a \`Message<...>\` with a \`null\` payload expecting every endpoint to accept it.

## 5. Flow Test: Checking Payload and Headers Through a Transformer

Unit tests only prove Java logic. Flow tests verify how Spring Integration actually passes a \`Message\` across channels and endpoints. The next example creates a flow:

~~~mermaid
flowchart LR
    A["normalize.in\npayload='  SKU-42  '\ntenantId='shop-a'"] --> B["Transformer\nString.trim()"]
    B --> C["Header Enricher\nstage='normalized'"]
    C --> D["normalize.out\nQueueChannel"]
~~~

Place the following code in \`src/test/java/example/PayloadHeaderFlowTest.java\`. This is a standalone test class using a \`QueueChannel\` to observe output messages, without needing an HTTP server or message broker:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PayloadHeaderFlowTest.Config.class)
class PayloadHeaderFlowTest {

    @Autowired
    @Qualifier("normalize.in")
    MessageChannel input;

    @Autowired
    @Qualifier("normalize.out")
    QueueChannel output;

    @Test
    void transformer_changes_payload_and_preserves_business_headers() {
        Message<String> request = MessageBuilder
                .withPayload("  SKU-42  ")
                .setHeader("tenantId", "shop-a")
                .setHeader("requestId", "req-7")
                .setHeader("attempt", 1)
                .build();

        assertThat(input.send(request)).isTrue();

        Message<?> response = output.receive(1_000);
        assertThat(response).isNotNull();
        assertThat(response.getPayload()).isEqualTo("SKU-42");
        assertThat(response.getPayload()).isInstanceOf(String.class);
        assertThat(response.getHeaders().get("tenantId"))
                .isEqualTo("shop-a");
        assertThat(response.getHeaders().get("requestId"))
                .isEqualTo("req-7");
        assertThat(response.getHeaders().get("attempt"))
                .isEqualTo(1);
        assertThat(response.getHeaders().get("stage"))
                .isEqualTo("normalized");
        assertThat(response.getHeaders())
                .containsKeys(MessageHeaders.ID, MessageHeaders.TIMESTAMP);
        assertThat(output.receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("normalize.out")
        QueueChannel normalizeOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow normalizationFlow() {
            return IntegrationFlow.from("normalize.in")
                    .transform(String.class, String::trim)
                    .enrichHeaders(h -> h.header("stage", "normalized"))
                    .channel("normalize.out")
                    .get();
        }
    }
}
~~~

The **observable contract** includes: payload is trimmed; \`tenantId\`, \`requestId\`, and \`attempt\` are preserved; \`stage\` is added with the expected value; and only **one** output message is produced. Although the Transformer creates a new message, the test does not compare the output's \`id\` or \`timestamp\` against the input's, because the framework may regenerate both values when constructing the new message.

**Limitation of \`receive(0)\`:** It works well when the entire flow segment runs synchronously. If the flow involves an \`ExecutorChannel\`, broker, or asynchronous endpoint, \`receive(0)\` only states that *no message is present at the moment of reading*. To assert that no extra message arrives during a specific window, design an observation window with a timeout and avoid assuming processing order when it is not guaranteed.

### When a Pipeline Intentionally Mutates Headers

A Header Enricher can **add** a header, **overwrite** an existing value, or only fill a default value, depending on configuration. Therefore, write tests expressing the policy chosen by the project:

| Policy | Input Header | Expected Output |
| --- | --- | --- |
| Add new value | No \`stage\` | \`stage="normalized"\` |
| Overwrite | \`stage="raw"\` | \`stage="normalized"\` |
| Add only if missing | \`stage="approved"\` | Keep \`stage="approved"\` |
| Strip internal header | \`internalToken="tmp"\` | \`internalToken\` no longer present |
| Keep business key | \`tenantId="shop-a"\` | Remains \`"shop-a"\` |

Do not guess an Enricher's behavior from the header name alone. Check the actual **Header Enricher**, **Header Filter**, or message-mapping logic being used. For sensitive information, verify that the header is not forwarded to an interface or system outside its contract.

## 6. Testing Router and Filter Based on Headers

A Router often reads headers like \`route\`, \`eventType\`, or \`tenantId\`. A bug might leave the payload unchanged yet send the message down the wrong branch.

~~~text
Input:
  payload = "SKU-42"
  route   = "priority"

Expected:
  priority.out  -> 1 message, payload is still "SKU-42"
  normal.out    -> 0 messages
  tenantId      -> unchanged
~~~

There should be at least three scenarios for a routing header:

1. First valid value: \`route="priority"\` goes to the priority channel.
2. Second valid value: \`route="normal"\` goes to the normal channel.
3. Missing or invalid \`route\` value: apply the **defined policy** (default channel, exception, discard, or error route)—never rely on unagreed implicit behavior.

Example mapping configuration in the Java DSL:

~~~java
@Bean
IntegrationFlow routeByPriority() {
    return IntegrationFlow.from("route.in")
            .route("headers['route']", r -> r
                    .channelMapping("priority", "priority.out")
                    .channelMapping("normal", "normal.out"))
            .get();
}
~~~

This snippet assumes \`priority.out\` and \`normal.out\` are channels registered in the context. In tests, use \`QueueChannel\` for both, send a message with \`route="priority"\`, read the priority output, and verify the normal output is empty. If either branch processes asynchronously, add an appropriate waiting mechanism.

A Filter can decide based on both payload **and** headers—for example, rejecting requests without a valid tenant. Extract the condition into a Java function for easy unit testing:

~~~java
static boolean hasValidTenant(Message<?> message) {
    Object value = message.getHeaders().get("tenantId");
    return value instanceof String tenant && !tenant.isBlank();
}

@Test
void tenant_validation_handles_absent_and_wrong_type() {
    Message<String> valid = MessageBuilder.withPayload("SKU-42")
            .setHeader("tenantId", "shop-a").build();
    Message<String> missing = MessageBuilder.withPayload("SKU-42")
            .build();
    Message<String> wrongType = MessageBuilder.withPayload("SKU-42")
            .setHeader("tenantId", 42).build();

    assertThat(hasValidTenant(valid)).isTrue();
    assertThat(hasValidTenant(missing)).isFalse();
    assertThat(hasValidTenant(wrongType)).isFalse();
}
~~~

When integrating this predicate into a Filter, also test the output and discard channels: valid messages proceed, and invalid messages are dropped according to policy. Never test only the predicate's return value and conclude that the flow has wired the channels correctly.

## 7. Testing Splitter, Aggregator, and Correlation Headers

When a Splitter divides a message into multiple elements, Spring Integration typically attaches metadata such as \`correlationId\`, \`sequenceNumber\`, and \`sequenceSize\` so downstream endpoints can process or regroup them. Exact outputs depend on sequence configuration and splitter type.

~~~mermaid
flowchart TD
    A["Input\npayload=['A','B']\nrequestId='r-01'"] --> B[Splitter]
    B --> C["'A'\ncorrelationId=G\nsequenceNumber=1\nsequenceSize=2"]
    B --> D["'B'\ncorrelationId=G\nsequenceNumber=2\nsequenceSize=2"]
    C --> E[Aggregator]
    D --> E
    E --> F["Output\n['A','B']"]
~~~

### Required Assertions After a Splitter

- **Payload** of each child message contains the individual element (e.g., \`"A"\` and \`"B"\`), not the whole list.
- **Message count** matches the expected element count; none lost or duplicated.
- **Required business headers** (e.g., \`requestId\`) are preserved if mandated by the contract.
- **Correlation** is identical across child messages of the same split and differs across distinct groups.
- **Sequence** has exact positions 1/2 and 2/2 if the flow enables/generates sequence metadata.

Do not assert a framework-generated correlation UUID against a fixed string. Capture the correlation ID of the first message and assert the second message shares the same value; verify it differs from the correlation ID of an independent request if that is part of the contract.

### Building Messages with Correlation Metadata to Test an Aggregator

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

static Message<String> part(
        String groupId, int position, int total, String payload) {
    return MessageBuilder.withPayload(payload)
            .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, groupId)
            .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, position)
            .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, total)
            .setHeader("requestId", "r-01")
            .build();
}
~~~

A good test interleaves two groups:

~~~text
Send A1 (correlationId=A, sequenceNumber=1, sequenceSize=2)
  -> no result yet
Send B1 (correlationId=B, sequenceNumber=1, sequenceSize=2)
  -> no result yet
Send B2 (correlationId=B, sequenceNumber=2, sequenceSize=2)
  -> emits group B: ["B1", "B2"]
Send A2 (correlationId=A, sequenceNumber=2, sequenceSize=2)
  -> emits group A: ["A1", "A2"]
~~~

Assert the aggregated payload, result count, emission timing, and group isolation. If using a persistent \`MessageGroupStore\`, custom release strategy, or timeout, add tests for duplicates, missing items, late arrivals, and expiration according to that policy. Never assume every Aggregator waits strictly for \`sequenceSize\` across all configurations.

## 8. Gateway, Retry, and Error Channel: Which Headers Matter?

### Gateway and replyChannel

A Gateway turns a Java call into a request message and returns the reply to the caller. When testing, verify:

- The payload passed to the gateway has the expected type and value.
- Business headers that the gateway is responsible for propagating are attached properly.
- The flow returns a reply conforming to the contract without losing required business fields.
- A finite timeout is configured for cases with no reply.

\`replyChannel\` is typically a header managed by the request/reply infrastructure. You do not need to assert the exact internal channel object in every test. What matters more is that the caller receives the accurate data and a single request does not yield multiple replies.

### Retry and Business Identity

Retry can invoke a handler multiple times for the same request. Use a \`requestId\` header or business idempotency key for tracking:

~~~text
Message:
  payload   = "charge-order-7"
  requestId = "req-7"

Attempt 1 -> handler fails transiently
Attempt 2 -> handler succeeds

Assert:
  handler invocation count = 2 (per maxAttempts=2 configuration)
  requestId observed on both attempts = "req-7"
  output has only one successful result
~~~

Distinguish **processing attempts** from **business messages**: retries increase invocation counts, but must not cause duplicate unintended side effects such as charging a payment twice. The \`requestId\` header is a tracking/idempotency tool only if the application actually enforces it; having the header alone does not automatically guarantee idempotency.

### ErrorMessage and Failure Data

In Spring Integration, errors can be thrown back to the caller (synchronous path) or published as an \`ErrorMessage\` (when an error handler/error channel is configured). Tests must match the execution model:

| Model | Test Behavior |
| --- | --- |
| \`DirectChannel\`, handler throws synchronously | Assert exception on \`send()\` or Gateway call |
| Asynchronous flow with error publishing | Read \`ErrorMessage\` from configured error channel |
| Retry with recovery | Assert recovery message/value or final error per contract |

For an \`ErrorMessage\`, the payload is a \`Throwable\` (often a \`MessagingException\` or related type), **not** the original business payload. To trace back to the original message, inspect \`failedMessage\` on exceptions that support this property or metadata preserved per configuration. Do not assume every exception carries all request headers: error wrapping and propagation depend on the endpoint and execution model.

In particular, adding an \`errorChannel\` header to a request does not automatically convert every synchronous exception into a message on that error channel. A proper error-channel test must build a flow with a matching error handler and verify both the dispatch path and the error content.

## 9. Assertions to Use vs. Assertions Prone to False Failures

| Should Assert | Should Avoid Unless Contractually Guaranteed |
| --- | --- |
| \`payload\` has right type and value | Asserting only that output is non-\`null\` |
| Business headers present, right type, right value | Comparing every header against the entire input map |
| Removed header is truly **no longer present** | Checking only \`get("key") == null\` when absence matters |
| Output has exact designed message count | Ignoring duplicate messages |
| Correlation identical within a group, isolated across groups | Comparing auto-generated correlation against a fixed string |
| Sequence accurate when flow guarantees sequence | Always assuming sequence is present |
| Exception or ErrorMessage follows configured path | Assuming all errors go to \`errorChannel\` |
| Finite timeout matching async model | Fixed sleep then inferring no message exists |
| Header values explicitly set by the application | Comparing auto-generated \`id\` or \`timestamp\` to fixed numbers |

To keep tests maintainable, place assertions close to where messages are sent and received. If there are multiple steps, verify each step's output in isolated tests before writing an end-to-end test. When a test fails, this pinpoints whether the fault lies in the Transformer, Router, Header Enricher, Splitter, or Aggregator.

### Notes on Type Conversion

Payloads may undergo type conversion, such as \`String\` to DTO or DTO to JSON. If the contract specifies a DTO:

~~~java
assertThat(response.getPayload()).isInstanceOf(OrderLine.class);
OrderLine line = (OrderLine) response.getPayload();
assertThat(line.sku()).isEqualTo("SKU-42");
assertThat(line.quantity()).isEqualTo(3);
~~~

If the contract specifies a JSON string, verify the data using a JSON parser instead of relying on field ordering or whitespace in the JSON string. Valid JSON content does not replace asserting the \`contentType\` header or encoding metadata if the receiving system depends on them.

## 10. Testing at Real Integration Boundaries

When crossing HTTP, Kafka, AMQP, or custom adapters, not every header in \`MessageHeaders\` is mapped to the external protocol. This is intentional: each adapter defines its own header mapper rules, serializers, and supported data types.

For example, in an internal flow, \`tenantId="shop-a"\` is a String. When sent over HTTP, it may need mapping to an appropriate HTTP header; when sent to a broker, it needs a header type permitted by the adapter. Boundary tests must assert the **values actually transmitted/received** across the adapter, not merely inspect the header map before sending.

A layered strategy:

1. **Unit tests** for mappers and payload/header predicates with small inputs.
2. **Flow tests** verifying messages across in-memory Spring Integration endpoints.
3. **Adapter/contract tests** verifying serialization, header mapping, encoding, timeouts, and external protocol errors.

Avoid logging access tokens, passwords, or secrets just to prove a header passed through. Log only what is needed for observability; for request identifiers or correlation IDs, use dummy data in tests.

## 11. Checklist and Practice Exercises

Before considering a payload/header test complete, check against these questions:

- Does the payload have the expected type and value after the endpoint?
- Do you need to check DTO structure, collection size, or encoding?
- Which headers must be present, absent, or stripped?
- Are business headers preserved with the right type, not just string representation?
- Did the Router send to exactly one branch, with other branches receiving nothing?
- Do correlation and sequence metadata properly support the Splitter/Aggregator flow?
- With retry, is the request ID preserved and the attempt count bounded?
- For errors, does the application actually use synchronous exceptions or ErrorMessage?
- Do assertions depend on UUIDs, timestamps, ordering, or timing that are not guaranteed?
- Can the test run independently, without relying on leftover messages in another test's channel?

### Exercise A: Modifying a Header

Extend the flow in section 5 with a Header Enricher endpoint that adds \`source="catalog"\`. Create a request containing only \`tenantId="shop-a"\`, then verify payload \`"SKU-42"\`, preserved tenant, and added \`source\`. Create another request that already has \`source="manual"\`, decide explicitly from business requirements whether to preserve or overwrite it, and write an assertion for that policy.

### Exercise B: Wrong Data Type

Create three messages with \`tenantId\` set to \`"shop-a"\`, absent, and integer \`42\`. Write a unit test for \`hasValidTenant\`. Wire the function into a Filter in a small flow, then verify the valid message proceeds and the other two are dropped/routed to the discard channel as configured.

### Exercise C: Two-Group Correlation

Send two elements for group A and two elements for group B in the order A1, B1, B2, A2. Using only the payload and the three headers \`correlationId\`, \`sequenceNumber\`, and \`sequenceSize\`, prove that:

1. No output is emitted before a group has all its elements.
2. The first result contains only group B's elements.
3. The second result contains only group A's elements.
4. There is no third result.

**Completion criteria:** Each test proves that the payload carries the **right data**, headers preserve the **right semantics**, and messages appear at the **right point** in the flow. When these contracts are clear, extending Routers, Filters, Transformers, Splitters, Aggregators, Gateways, retries, and error handling becomes safer because mismatches are caught immediately at the boundary where they arise.
