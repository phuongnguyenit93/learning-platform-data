# Messages with null payloads and how to represent absence

In **Spring Integration**, a message is the unit of exchange between endpoints of an **Enterprise Integration Patterns** (EIP) flow. A message typically contains a **payload** — the data to be processed — and **headers** — metadata for orchestration, correlation, routing, tracing, or error handling. So if a business lookup finds no data, or an external system sends a `null` value, can we create a `Message` with a `null` payload?

**Short answer:** With Spring's standard message APIs (`org.springframework.messaging.Message<T>`, `GenericMessage<T>`, and `MessageBuilder`), **an existing message's payload must not be `null`**. Distinguish clearly between **no message**, **a message whose payload is an object representing absence**, **a message containing an object with a `null` field**, and **a `null` value at an external protocol layer**. These cases have different meanings and handling strategies.

After this lesson, you will know how to:

- Explain the non-null payload rule in Spring Messaging and Spring Integration.
- Design suitable representations for not-found results, optional data, empty notifications, or deletion events.
- Distinguish a `null` in the payload from no message/reply, missing headers, and JSON or broker `null` values.
- Choose Filter, Router, Transformer, Gateway, `nullChannel`, and error channel for their proper purpose without losing business semantics.
- Test branches with no data or no response.

## 1. Core rule: a `Message` payload must not be null

Spring provides the message interface following this model:

```java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

This is the minimal shape to grasp the concept; not a full declaration of all framework components. In standard message-building approaches, the payload must be non-`null`. For example:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> valid = MessageBuilder.withPayload("hello").build();

// INVALID: null payload is rejected when building a message.
Message<String> invalid = MessageBuilder.withPayload((String) null).build();
```

The second call throws `IllegalArgumentException` due to violating the non-null payload precondition. This also applies when instantiating `GenericMessage` normally. Even if the type parameter is `Message<Object>` or `Message<Void>`, the type name **creates no exception** to this rule.

```text
Existing Message
├── payload  = NON-null object          ✓
└── headers  = message metadata

Message with payload = null             ✗ (cannot be created with standard APIs)
No message/reply                        ✓ (completely different state)
Message with payload = Optional.empty   ✓ (Optional is a non-null object)
Message with payload = NoData.INSTANCE  ✓ (marker is a non-null object)
```

**Why distinguish?** When endpoints process `Message<?>`, the framework may assume a payload exists and use it to select handlers, convert types, filter, or route. If business logic has a “no value” state, that state must be represented explicitly rather than relying on passing `null` as the entire payload.

## 2. Five states that are easily conflated

| State | Example | Is it a `Message` with a null payload? | Proper interpretation |
| --- | --- | --- | --- |
| No message emitted | Filter drops the input | No | There is no output message on that branch. |
| Message exists, “not found” result | Payload `NotFound("ORD-404")` | No | Payload is a valid business value. |
| Message has an object with a null field | `new LookupData("ORD-404", null)` | No | The overall payload is non-null; an inner field may be null per contract. |
| Message contains an empty value | `""`, `List.of()`, `new byte[0]` | No | An empty value differs from `null`; meaning is defined by the data contract. |
| External protocol has null | JSON `null`, Kafka record with null value | Not necessarily | That is a protocol representation; the adapter must handle and map it properly. |

### No reply does not mean a reply containing null

In a request–reply flow, a handler may produce no return value; the Gateway may receive no reply and follow its configured timeout or error policy. You cannot conclude that a `Message` with a `null` payload existed. Similarly, a Java method returning `null` does not automatically create a valid `Message<T>` with a `null` payload: subsequent behavior depends on the endpoint type and reply contract.

### A missing header field is not a null payload either

Headers are optional metadata. For example, `message.getHeaders().get("traceId")` may return `null` when the `traceId` key does not exist; yet the message's payload remains non-null. With `MessageBuilder`, setting a header with a `null` value acts as an instruction not to keep that header, not as a way to set a null payload.

## 3. Representing absence according to business needs

There is no single representation suitable for every flow. The right question is: **which states must the receiver distinguish, and must they be preserved when sent across another system?**

### Approach A — Explicit business result types: preferred when a response is needed

Suppose a Gateway looks up an order. “Not found” is a **normal outcome**, not a message-delivery failure. You can use a closed result hierarchy (*sealed hierarchy*) in Java 17+:

```java
import java.math.BigDecimal;
import java.util.Optional;

record FindOrder(String orderId) {}
record OrderInfo(String orderId, BigDecimal totalAmount) {}

sealed interface FindOrderResult permits Found, NotFound {}
record Found(OrderInfo order) implements FindOrderResult {}
record NotFound(String orderId) implements FindOrderResult {}

interface OrderRepository {
    Optional<OrderInfo> findById(String orderId);
}

class OrderLookup {
    private final OrderRepository repository;

    OrderLookup(OrderRepository repository) {
        this.repository = repository;
    }

    FindOrderResult lookup(FindOrder command) {
        return repository.findById(command.orderId())
                .<FindOrderResult>map(Found::new)
                .orElseGet(() -> new NotFound(command.orderId()));
    }
}
```

The result can be placed into a message like any valid payload:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

FindOrderResult result = new NotFound("ORD-404");
Message<FindOrderResult> reply = MessageBuilder.withPayload(result)
        .setHeader("traceId", "trace-123")
        .build();
```

Advantage: readers and Routers can distinguish `Found`/`NotFound` by type without guessing from an arbitrary null value. The `traceId` field is purely tracking metadata and does not affect the meaning of the result.

### Approach B — `Optional.empty()` in payload: suitable for controlled internal scopes

`Optional.empty()` **differs from `null`**: it is an object representing “no value.” Thus under the payload rule, this is a valid message:

```java
import java.util.Optional;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<Optional<String>> message = MessageBuilder
        .withPayload(Optional.<String>empty())
        .build();

boolean absent = message.getPayload().isEmpty(); // true
```

However, `Optional` is primarily suited as a Java API return type. **Do not default to using it as a durable message contract or across process boundaries**, because serializers and receiver schemas may not represent the same semantics; `Optional` was not designed as a universal wire data format either. For cross-system integration messages, types like `Found`/`NotFound` or an explicit result schema usually interoperate better.

### Approach C — Marker/sentinel: for internal control messages

If you need to send a signal without detailed data, you can use a **non-null** marker:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

enum NoData {
    INSTANCE
}

Message<NoData> signal = MessageBuilder.withPayload(NoData.INSTANCE)
        .setHeader("reason", "refresh-completed")
        .build();
```

This can make sense for an internal flow. However, `NoData.INSTANCE` **is not a general concept automatically understood by Spring**; it only carries meaning if all involved handlers and converters agree on the type and handling. If data must travel over JSON/broker, design and test the serialized format of that signal rather than passing an arbitrary enum without a contract.

### Approach D — Object with nullable fields: when only an attribute can be absent

Sometimes the payload is a multi-field result and **only a subset of information is allowed to be absent**:

```java
record CustomerProfile(String customerId, String secondaryEmail) {}

CustomerProfile profile = new CustomerProfile("CUS-08", null);
// profile is non-null; secondaryEmail may be null per business contract.
```

Define clearly: does `secondaryEmail == null` mean “unknown”, “not provided”, or “deleted”? If those states differ, a single nullable field is insufficient; use an explicit status or a schema distinguishing *missing* from *explicit null*.

### Approach E — Empty collection/string/bytes: only when “empty” truly has meaning

`List.of()`, `""`, and `new byte[0]` are all non-null and can serve as payloads when the type fits. However, an **empty list** usually means “queried, 0 items found,” whereas **no result** may mean “not queried,” “not authorized to return data,” or “not found.” Do not collapse these cases into one representation if business logic needs to tell them apart.

## 4. JSON representation and external protocols

In JSON, the following representations are not equivalent:

```json
{}
```

```json
{"customerEmail": null}
```

```json
{"customerEmail": ""}
```

```json
{"status": "NOT_FOUND", "orderId": "ORD-404"}
```

An omitted field, a field with `null`, an empty string, and a not-found result are four different situations. For an API contract, explicitly document which fields are required, nullable, and which states are permitted.

Important note: a message whose payload is the **string** `"null"` still has a non-null payload — specifically the four characters `n`, `u`, `l`, `l` — even though a JSON parser could interpret that string content as the JSON `null` value. When a content converter reads a top-level null value, decide whether the system should **preserve the information via a valid substitute type**, discard it by policy, or raise an error, rather than trying to force `MessageBuilder` to accept `null`.

### The Kafka tombstone case

In Kafka, a record with **record value = null** carries protocol semantics, typically a *tombstone* for a compacted topic. That is not a valid Spring `Message<?>` with a null payload. When passing through Spring messaging APIs, the Kafka adapter or integration must have a way to represent that state (for example, Spring Kafka's `KafkaNull.INSTANCE` marker in appropriate flows) and map it properly to a transport null value.

**Do not assume** that `MessageBuilder.withPayload(null)` produces a Kafka tombstone, or that every adapter understands `KafkaNull`. Exact handling depends on version, integration library, serializer, endpoint configuration, and producer/consumer contracts. For this problem, distinguishing **broker null values** from **Spring Message payloads** is mandatory.

## 5. When needing “do not send further,” use the right EIP instead of a null payload

Some problems do not require returning a message expressing “no data”; the real requirement is simply to **stop processing an invalid or unsuitable message**. In that case, choose the pattern built for that purpose.

| Purpose | Pattern/mechanism | Expected behavior |
| --- | --- | --- |
| Discard requests failing a condition | **Filter** | Does not forward the message to the accepted branch. |
| Choose branch by status | **Router** | Routes a message with a valid payload to the corresponding branch. |
| Convert input data into a typed result | **Transformer** | Returns a new non-null payload, e.g. `Found` or `NotFound`. |
| Intentionally drop a message | **`nullChannel`** | Receives and discards the message; does not turn payload into null. |
| Synchronous response to caller | **Gateway** | Designs a contract with an explicit reply or timeout/no-reply handling. |
| Report processing error | **Error channel / ErrorMessage** | Sends error details through error mechanisms, never by setting a null payload. |

### Example 1: Filter discarding unqualified input

A simple example using Spring Integration annotations:

```java
import org.springframework.integration.annotation.Filter;
import org.springframework.stereotype.Component;

record SubmitOrder(String orderId, long amount) {}

@Component
class OrderValidationFilter {

    @Filter(
        inputChannel = "ordersInput",
        outputChannel = "ordersAccepted",
        discardChannel = "nullChannel"
    )
    public boolean accept(SubmitOrder order) {
        return order.orderId() != null
                && !order.orderId().isBlank()
                && order.amount() > 0;
    }
}
```

If `accept()` returns `false`, the message does not proceed to `ordersAccepted`; it is routed to `nullChannel` to be discarded per the illustrative configuration. **No output message on the accepted channel** is the result of Filter, not a message with a null payload. In a real system, you can use a **discard channel** for controlled logging, metrics, or handling rejected requests instead of silently dropping them.

### Example 2: Transformer still emits a valid result when not found

```java
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
class FindOrderTransformer {
    private final OrderLookup lookup;

    FindOrderTransformer(OrderRepository repository) {
        this.lookup = new OrderLookup(repository);
    }

    @Transformer(
        inputChannel = "findOrderRequests",
        outputChannel = "findOrderResponses"
    )
    public FindOrderResult transform(FindOrder request) {
        return lookup.lookup(request); // Found or NotFound; never returns null.
    }
}
```

In this example, the `record`, `interface`, and `OrderLookup` defined in Section 3 are reused. The Transformer returns a `Found` or `NotFound` payload so both cases can still be observed and tested by a Router, another service, or a Gateway. If a data store access error occurs, do not disguise that error as `NotFound`; let the appropriate error-reporting/recovery mechanism handle it.

### Example 3: Distinguishing not-found results from real errors

```text
FindOrder request
       │
       ▼
  Order lookup
       │
       ├── Found ──────────────► Message<Found>
       │
       ├── Not found ──────────► Message<NotFound>
       │
       └── Data access error ──► Exception / error flow

Filter drops message ──────────► No message on output channel
```

Spring Messaging's `ErrorMessage` holds an **exception** as its non-null payload. Therefore, “order not found” (a valid business outcome) and “database unreachable” (an incident) should never be collapsed into a single `null` signal.

## 6. Gateway, Splitter/Aggregator, correlation, and retry

**Gateway:** For request–reply calls, decide whether “not found” returns a `NotFound`, whether the caller is allowed to receive no reply, and how timeouts are handled if no reply arrives. A Gateway method returning `null` in a no-reply/timeout scenario (if configuration allows) **does not prove** a Spring message with a null payload existed. For synchronous business APIs, a typed result is usually easier to control than an implicit absence of reply.

**Splitter:** If the input contains an empty list, the flow may produce zero element messages. An empty list is a **valid input payload**, yet that does not mean the Splitter creates a child message with a null payload. If business logic needs “finished processing with zero items,” design an independent signal or reply when needed.

**Aggregator:** Aggregator only collects messages that were created and received at its input. Having **zero child messages** does not generate a “null” element for the Aggregator to close the group automatically; design group completion conditions, timeouts, empty-result handling, or completion notification channels per problem requirements. `correlationId` and `sequenceSize` help group and track progress when messages exist, but do not represent a null payload themselves.

**Retry:** A retry creates a new processing or delivery attempt without changing the payload definition. If a branch yields no data because the record genuinely does not exist, blind retries will not help; if the failure is transient, handle it with an explicit retry policy and error flow. Do not use `null` as a signal meaning “not found,” “retry,” and “error” all at once, as it makes monitoring hard and causes wrong handling.

**Observability:** When tracing a flow, record statuses such as `FOUND`, `NOT_FOUND`, `FILTERED`, `TIMED_OUT`, `FAILED` with appropriate correlation ID/trace ID. These statuses cannot be safely inferred from an ambiguous `null`. Avoid putting sensitive personal data into headers or logs solely for tracing convenience.

## 7. Testing null boundaries and empty values

Minimum checks should include:

1. **Cannot create a message with a null payload:** verify constructors/builders reject `null`.
2. **Valid absence representations:** messages with `NotFound` or `Optional.empty()` can be created and take the right branch.
3. **Nullable fields:** null fields inside payload objects are read properly when the schema allows them.
4. **Filter does not forward:** rejected inputs do not appear on the output channel; if monitoring is needed, verify the discard channel receives the original message.
5. **Gateway with no reply:** verify timeout, reply-required policy, and error reporting per actual configuration rather than assuming all Gateways behave identically.
6. **Codec/adapter:** test JSON `null`, missing/nullable fields, empty bytes, Kafka tombstones, and header mapping for the actual transport used.

A short unit test for the payload rule:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessagePayloadTest {

    @Test
    void rejectNullPayload() {
        assertThrows(IllegalArgumentException.class,
                () -> MessageBuilder.withPayload((String) null).build());
    }

    @Test
    void notFoundIsAValidPayload() {
        Message<FindOrderResult> message = MessageBuilder
                .<FindOrderResult>withPayload(new NotFound("ORD-404"))
                .build();

        NotFound payload = assertInstanceOf(NotFound.class, message.getPayload());
        assertEquals("ORD-404", payload.orderId());
    }
}
```

When testing actual integration flows, add the corresponding channel configurations, Spring Integration dependencies, adapter environment, and test fixtures. The JUnit example above checks the `Message` class and result types, **not replacing** end-to-end tests of the full Filter, Transformer, or Gateway.

## 8. Hands-on scenario: which representation to choose?

Suppose a warehouse system receives a request to check a product code. Consider these scenarios:

| Scenario | Recommended representation | What not to do |
| --- | --- | --- |
| Product code does not exist | `ProductNotFound(productId)` in payload | Return `null` and leave the caller guessing the cause. |
| Product exists, secondary description not yet entered | `ProductInfo` with nullable description field or explicit status | Equate missing description with a non-existent product. |
| Inventory list queried and returns 0 rows | `InventoryResult(items = [])` | Treat an empty list as a system error. |
| Message should not proceed to next processing branch | Filter or Router/discard channel | Create a message with a null payload to “stop the flow.” |
| Warehouse service timed out | Timeout / error flow / `Unavailable` result if part of contract | Equate timeout with `ProductNotFound`. |
| Need to delete a key from a Kafka compacted topic | Tombstone per Kafka contract, mapped via adapter | Use `MessageBuilder.withPayload(null)` as a way to emit a tombstone. |

**Reasoning exercise:** If the warehouse system returns JSON `{ "status": "NOT_FOUND" }`, the Spring application receives a non-null JSON string and parses it into `ProductNotFound`. If the system instead returns top-level JSON `null`, a converter might produce a Java null value. Design a **validation/translation step before building the output Spring message**: distinguish “intentional not found,” “invalid empty payload,” and “decoding error” using distinct result types or error flows. When a flow involves multiple adapters, test every boundary so status semantics are never lost.

## Summary

- Spring `Message<T>` created via standard APIs **does not allow a null payload**; `Message<Void>` is not a workaround for this rule either.
- **No message**, **no reply**, **missing header**, **payload containing a null field**, and **protocol-level null** are distinct concepts.
- When “not found” is a business outcome, use an **explicit result type** such as `Found`/`NotFound`; `Optional.empty()` or a non-null marker is suitable only when the contract allows it.
- When needing **not to forward a message**, use **Filter**, Router, or `nullChannel`, rather than trying to build a message with a null payload.
- When needing to **report an error**, use error flows/exceptions and suitable retry policies; do not mix errors, timeouts, and not-found states.
- When connecting external systems, explicitly design nullable JSON fields, adapter mappings, and special cases like **Kafka tombstones** so Spring Integration preserves business semantics, testability, and traceability.
