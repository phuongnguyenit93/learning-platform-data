# Message and Java Objects

This lesson belongs to the **Message** chapter of the **SPRING_INTEGRATION_CORE** module. Within the scope of designing flows with Message, MessageChannel, endpoints, gateways, and the Java DSL, it clarifies the relationship between business objects and messages. This is foundational for deciding which data a transformer changes, where a router or filter reads information, what an aggregator uses to identify groups, and which parts of a message tests must observe.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Distinguish a Java object used as business data from the `Message<T>` wrapping that data.
- Create and read messages using the right Spring Messaging classes.
- Explain why a payload or header value can still change despite using an immutable message.
- Choose method signatures accepting the payload, headers, or the entire message.
- Trace payload replacement and header propagation through a Java DSL flow.
- Distinguish in-memory reference passing from format conversion across system boundaries.

You need to know classes, interfaces, generics, collections, and beans in Spring. Examples use Java 17 syntax; when choosing a Spring version for an actual project, satisfy that version's JDK requirements. The flow sections require `spring-integration-core` and corresponding Spring dependencies; tests use JUnit Jupiter. Small illustrative snippets are standalone, while the `MessageObjectDemo` example is a complete class.

## 2. From Business Object to Message

Suppose a system receives an order approval request:

~~~java
import java.math.BigDecimal;

public record OrderRequest(String orderId, BigDecimal amount) {
}
~~~

`OrderRequest` describes the business data. It does not yet say which sales channel the request came from or where the reply should be sent.

`Message<T>` adds a wrapper comprising payload and headers. The interface resides in package `org.springframework.messaging`; `T` represents the payload type. The two core methods are `getPayload()` and `getHeaders()`. See [Message API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html).

~~~java
import org.springframework.messaging.Message;

// Illustrates reading; not redefining Spring's interface.
OrderRequest order = message.getPayload();
String source = message.getHeaders().get("source", String.class);
~~~

The snippet above assumes `message` has type `Message<OrderRequest>`. You can picture the relationship as follows:

~~~mermaid
flowchart LR
    P["OrderRequest: business data"] --> M["Message&lt;OrderRequest&gt;"]
    H["Headers: source, operationId, replyChannel"] --> M
    M --> C["MessageChannel"]
    C --> E["Endpoint invokes handler method"]
~~~

| Component | Question It Answers | Example |
| --- | --- | --- |
| Payload | What content is being processed? | Order ORD-1001 worth 125000 |
| Headers | What context or directives does the flow need? | Source WEB, operation ID, reply address |
| Message | What unit of data moves through the flow? | Payload accompanied by headers |
| MessageChannel | Where in the flow is the message sent? | `orderInput` |
| Endpoint | Which step receives and processes the message? | Normalizing the request, calling the order approval service |

A Java object does not need to extend a special business base class just to serve as a payload. Conversely, placing an object into a message does not automatically turn it into a business event: whether it means a command, event, or processing result must still be expressed in the application's contract.

For example, `OrderRequest` is a request to perform an action; `OrderAccepted` is the outcome of accepting the order. The class names and fields of these two types help flow readers clearly understand the business state transition.

## 3. Creating a Message from an Object

`GenericMessage<T>` is a common implementation of `Message<T>`. You can pass the payload alone or pass it together with a `Map` of headers; the payload must not be `null`. The constructor taking a `Map` copies the map's key–value pairs without deep-cloning the objects inside. See [GenericMessage API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/GenericMessage.html).

~~~java
import java.math.BigDecimal;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

OrderRequest order =
        new OrderRequest("ORD-1001", new BigDecimal("125000"));

Message<OrderRequest> message = new GenericMessage<>(
        order,
        Map.of("source", "WEB", "operationId", "accept:ORD-1001")
);

OrderRequest payload = message.getPayload();

System.out.println(payload.orderId());                // ORD-1001
System.out.println(payload == order);                 // true
System.out.println(message.getHeaders().get("source")); // WEB
~~~

In the example, `payload == order` is true because the message holds a reference to the passed-in object. There is no step converting the object to JSON and reconstructing it.

You can use `MessageBuilder` when headers need to be described more clearly:

~~~java
import org.springframework.messaging.support.MessageBuilder;

Message<OrderRequest> message = MessageBuilder
        .withPayload(order)
        .setHeader("source", "WEB")
        .setHeader("operationId", "accept:ORD-1001")
        .build();
~~~

This lesson consistently uses `org.springframework.messaging.support.MessageBuilder`. Spring Integration also has a builder in its own support package; when reading examples or using an IDE, verify the import rather than looking only at the short class name.

There is no need to create a custom subclass like `OrderMessage extends GenericMessage<OrderRequest>` just to represent each kind of order. Keeping business semantics in the payload type usually makes the contract easier to read and avoids multiplying wrapper classes that add no new behavior.

## 4. Putting Information in Payload or Headers?

A useful way to divide responsibilities is to look at who needs to use the information.

- Payload holds data that business services need to understand and perform the operation.
- Headers hold context that the integration mechanism uses to transport, trace, route, or reply.

This is a contract design decision, not a rigid rule that a field must always live in one place.

| Information | Appropriate Location in the Example | Reason |
| --- | --- | --- |
| `orderId`, `amount` | Payload | Determines which order is approved and for what amount |
| `source` | Header | Distinguishes ingestion source for tracking or branching |
| `operationId` | Header per application contract | Identifies a processing request across multiple steps |
| `replyChannel` | Framework header | Specifies the reply path in request–reply |
| `tenantId` used for policy evaluation | Requires an explicit contract | Must be present wherever permission checks and policy enforcement need it |

If you decide `tenantId` lives only in a header, the service signature or orchestration layer must explicitly pass it to the business logic that needs it. Avoid letting business logic silently depend on a header that the contract never mentions.

`MessageHeaders` provides constants for system headers such as `ID`, `TIMESTAMP`, `REPLY_CHANNEL`, and `ERROR_CHANNEL`. Typed getters assist in reading values with the expected type; they do not automatically convert strings to numbers or JSON to DTOs. See [MessageHeaders API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html).

~~~java
import java.util.UUID;

UUID messageId = message.getHeaders().getId();
Long createdAt = message.getHeaders().getTimestamp();
String source = message.getHeaders().get("source", String.class);
~~~

If a custom header is absent, the getter may return `null`; the application must define whether that header is required or has a default value.

`operationId` in this lesson is an application-assigned header, not an automatic Spring deduplication feature. To prevent duplicates, pair that value with an appropriate state storage and checking mechanism.

## 5. Message Immutability and Object Mutability

### 5.1. An Immutable Shell Does Not Mean an Immutable Object Graph

With `GenericMessage` and ordinary message construction, there is no setter to reassign the payload. The public headers map also forbids `put`, `remove`, or `clear`. Even so, the payload and objects used as header values may still be mutable. The [Spring Integration Message documentation](https://docs.spring.io/spring-integration/reference/message.html) clearly states this boundary.

The following example does not swap the payload for another object; it mutates the very object the message is referencing:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

List<String> orderIds = new ArrayList<>();
orderIds.add("ORD-1001");

Message<List<String>> message = new GenericMessage<>(orderIds);

orderIds.add("ORD-1002");

System.out.println(message.getPayload());
// [ORD-1001, ORD-1002]
~~~

Readers of the message see two order IDs. If the goal was to capture a snapshot of the data at send time, the code above fails that contract.

### 5.2. Copying the Header Map Does Not Copy Objects Inside Headers

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

List<String> stages = new ArrayList<>();
Map<String, Object> rawHeaders = new HashMap<>();
rawHeaders.put("source", "WEB");
rawHeaders.put("stages", stages);

Message<String> message = new GenericMessage<>("ORD-1001", rawHeaders);

rawHeaders.put("source", "BATCH");
stages.add("RECEIVED");

System.out.println(message.getHeaders().get("source")); // WEB
System.out.println(message.getHeaders().get("stages")); // [RECEIVED]
~~~

Changing the `source` entry in the original map does not change the message's map. However, `stages` in both places points to the same list, so the list's contents still change.

Putting an object with setters into the payload or a header creates the exact same kind of issue. Examine nested objects too, not just the `final` modifier on the outermost variable.

### 5.3. Records and Collections Must Be Designed Together

A Java record is a shallowly immutable data carrier: component fields are `final`, but referenced objects are not necessarily immutable. You can use a constructor to validate data and perform defensive copies. See [Record API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

~~~java
import java.util.List;

public record OrderBatch(List<String> orderIds) {

    public OrderBatch {
        orderIds = List.copyOf(orderIds);
    }
}
~~~

With `List<String>`, this approach works well to keep the list unmodifiable through standard APIs. `List.copyOf` creates a structurally unmodifiable list that does not reflect subsequent structural changes to the source collection; it does not clone individual elements. See [List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

If `String` were replaced by `MutableOrder`, each element would still need its own policy: convert to an immutable DTO, copy the necessary data, or ensure exclusive ownership.

### 5.4. Consequences When Multiple Branches Share a Payload

Suppose one branch sends an email and another writes history. If both mutate the same `Order`, the history log may reflect the state just altered by the email branch instead of the initial data.

The design should choose one of these clear directions:

1. Use immutable payloads and header values.
2. Create a new output object when changing data.
3. Make a sufficiently deep copy at boundaries requiring data isolation.
4. Use mutable objects only when ownership and processing order contracts are strictly controlled.

Synchronizing on a list to avoid race conditions does not automatically satisfy the requirement that "each branch sees the initial data." Synchronization and data isolation are two different requirements.

## 6. Creating the Next Message Without Mutating the Input Message

Suppose the ingestion step adds a `validated` header:

~~~java
Message<OrderRequest> validated = MessageBuilder
        .fromMessage(message)
        .setHeader("validated", true)
        .build();
~~~

The builder takes the payload and headers as initial data and constructs a message with the requested changes. When you want to change the payload type, start with `withPayload` and choose the headers to keep:

~~~java
public record OrderAccepted(String orderId, String status) {
}

OrderAccepted accepted =
        new OrderAccepted(message.getPayload().orderId(), "ACCEPTED");

Message<OrderAccepted> reply = MessageBuilder
        .withPayload(accepted)
        .copyHeaders(message.getHeaders())
        .setHeader("processedBy", "order-service")
        .build();
~~~

`copyHeaders` copies key–value pairs and may overwrite ordinary headers already set on the builder; `copyHeadersIfAbsent` preserves existing values. `id` and `timestamp` are not overwritten by copying. See [MessageBuilder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html).

Design consequences in the example:

- The `OrderRequest` object is not mutated.
- The output payload is a new `OrderAccepted`.
- The `operationId` header can continue forward to connect steps of the same request.
- The message's ID is managed by the framework; do not use it in place of a business key that stays stable across message rebuilds.

Do not infer that two timestamps must differ: two messages can be created within the same millisecond. Also do not treat calling `build()` without changes as proof that objects were deep-copied.

The snippet using `copyHeaders` illustrates an internal flow intentionally preserving context. When designing a contract toward external systems, select allowlisted headers rather than forwarding everything by default.

## 7. How Do Endpoints Connect Messages to Java Methods?

A business service can accept only the data it needs:

~~~java
public OrderAccepted accept(OrderRequest request) {
    return new OrderAccepted(request.orderId(), "ACCEPTED");
}
~~~

When a service activator endpoint invokes this method, Spring Integration extracts the payload from the message as the argument. If the method returns a plain object, the endpoint builds a message reply. When context needs to be read, you can use `@Header` or accept `Message<?>`. See [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

| Signature | Suitable When | Coupling to Messaging |
| --- | --- | --- |
| `accept(OrderRequest request)` | Only business data is needed | Low |
| `accept(OrderRequest request, @Header("source") String source)` | A specific header is needed | Coupled to messaging annotations |
| `accept(Message<OrderRequest> message)` | The entire envelope is needed | Directly coupled to `Message` |

Example accepting a header:

~~~java
import org.springframework.messaging.handler.annotation.Header;

public OrderAccepted accept(
        OrderRequest request,
        @Header("source") String source) {

    return new OrderAccepted(
            request.orderId(),
            "ACCEPTED_FROM_" + source
    );
}
~~~

These are alternative signature choices. Do not declare all of them as same-named overloads and expect the framework to guess which business method you intended.

A gateway lets callers work with an interface taking and returning Java objects; the proxy handles entering the flow and receiving the reply. In standard request–reply, the gateway may place a temporary reply channel in the `replyChannel` header. See [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

Thus, both entry points and business services can use DTOs, while messages serve as the exchange model between integration components. If a flow ends with an explicit output channel, a corresponding reply path must be designed; do not assume every returned DTO automatically reaches the gateway.

## 8. Complete Example: Java Objects Flowing Through a Java DSL Flow

The example receives an `OrderRequest`, strips whitespace from the order ID, invokes a Java service, and sends `OrderAccepted` to the output channel.

`IntegrationFlow` must be registered as a bean; the Java DSL describes channels and endpoints in Spring configuration. See [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

~~~mermaid
flowchart LR
    A["Message&lt;OrderRequest&gt;"] --> B["orderInput: DirectChannel"]
    B --> C["Transformer: normalize orderId"]
    C --> D["Service Activator: OrderService.accept"]
    D --> E["orderOutput: QueueChannel"]
    E --> F["Message&lt;OrderAccepted&gt;"]
~~~

Place the class below in a file named `MessageObjectDemo.java` in a practice project that already has dependencies. The records are nested inside the class so the example does not need extra Java files.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class MessageObjectDemo {

    public record OrderRequest(String orderId, BigDecimal amount) {
        public OrderRequest {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(amount, "amount");
        }
    }

    public record OrderAccepted(String orderId, String status) {
    }

    public static class OrderService {

        public OrderAccepted accept(OrderRequest request) {
            if (request.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            if (request.amount().signum() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            return new OrderAccepted(request.orderId(), "ACCEPTED");
        }
    }

    @Bean
    public MessageChannel orderInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderOutput() {
        return new QueueChannel(10);
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow
                .from("orderInput")
                .transform(
                        OrderRequest.class,
                        request -> new OrderRequest(
                                request.orderId().strip(),
                                request.amount()
                        )
                )
                .handle(orderService, "accept")
                .channel("orderOutput")
                .get();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(MessageObjectDemo.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);
            QueueChannel output =
                    context.getBean("orderOutput", QueueChannel.class);

            OrderRequest original =
                    new OrderRequest(" ORD-1001 ", new BigDecimal("125000"));

            Message<OrderRequest> request = MessageBuilder
                    .withPayload(original)
                    .setHeader("source", "WEB")
                    .setHeader("operationId", "accept:ORD-1001")
                    .build();

            if (!input.send(request)) {
                throw new IllegalStateException("Request was not accepted");
            }

            Message<?> reply = output.receive(1_000);

            if (reply == null) {
                throw new IllegalStateException("No result received");
            }
            if (!(reply.getPayload() instanceof OrderAccepted accepted)) {
                throw new IllegalStateException("Unexpected payload type");
            }

            System.out.println(accepted);
            System.out.println(reply.getHeaders().get("source"));
            System.out.println(reply.getHeaders().get("operationId"));
            System.out.println("Original unchanged: "
                    + original.orderId().equals(" ORD-1001 "));
        }
    }
}
~~~

Expected output from the four print statements executed by the example, ignoring Spring startup logs:

~~~text
OrderAccepted[orderId=ORD-1001, status=ACCEPTED]
WEB
accept:ORD-1001
Original unchanged: true
~~~

### 8.1. Points to Observe

1. `original` still keeps the ID with spaces. The transformer creates a different `OrderRequest` rather than mutating the input object.
2. The service only accepts `OrderRequest` and returns `OrderAccepted`; it does not read channels or build messages.
3. The output channel contains a message with an `OrderAccepted` payload.
4. Both custom headers remain present under the default header propagation behavior of the endpoints in the example.

A transformer can accept/return a payload or an entire message. When returning a payload, the framework preserves header context according to the endpoint's rules. When a transformer returns a complete `Message`, the transformer code is responsible for building the full output message. See [Transformer](https://docs.spring.io/spring-integration/reference/transformer.html).

That is why you must distinguish "a method returning a new DTO" from "a method manually building a new envelope." If you build a message manually in a transformer and forget `operationId` or a needed `replyChannel`, the flow can lose context even though the payload is right.

### 8.2. Why Doesn't the Example Need a Poller Yet?

`DirectChannel` invokes subscribers in a normal synchronous processing flow. `QueueChannel` holds the result so `main` can actively call `receive`. The example configures no endpoint automatically consuming the queue, so no poller needs to be added for this read step. Channel characteristics are described at [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Putting a message into a queue does not automatically create a consumer or a background business task. To have an endpoint process messages pulled from a queue, configure a corresponding consumption mechanism.

In this example, `send` returns normally only after the synchronous steps have placed the result onto the queue. In a flow with an executor, poller, or broker, a successful send does not automatically prove all downstream business work has finished.

## 9. Java Types, Data Conversion, and System Boundaries

### 9.1. Generics Aid Reading the Contract, Not Runtime Enforcement

`Message<OrderRequest>` tells the compiler what type the code is manipulating. However, `MessageChannel` is an abstraction accepting messages, not a `MessageChannel<OrderRequest>` that guarantees every producer sends the right DTO.

Another producer can still send a `Message<String>` into the same channel unless the application enforces additional constraints. Therefore, agree on each channel's payload contract and write tests for invalid inputs.

When holding `Message<?>`, check the type explicitly:

~~~java
Object payload = incoming.getPayload();

if (!(payload instanceof OrderRequest request)) {
    throw new IllegalArgumentException("Expected OrderRequest");
}

// From here on, use request as type OrderRequest.
~~~

Do not cast the message to "convert" data:

~~~java
// Such a cast does not parse JSON or create an OrderRequest.
// Message<OrderRequest> typed = (Message<OrderRequest>) rawMessage;
~~~

With collections, checking that the payload is a `List` does not prove every element is an `OrderRequest` either. The data contract must describe element types as well when that matters.

### 9.2. Type Conversion Requires a Concrete Mechanism

A method accepting `OrderRequest` does not mean every JSON string sent to the channel automatically becomes an `OrderRequest`. If the input is JSON, an appropriately configured adapter, converter, or transformer is needed.

An intentional pipeline might look like:

~~~text
HTTP body or byte[]
    -> decode and map data
    -> OrderRequest
    -> validate data
    -> business processing flow
~~~

This boundary should check at least: required fields, data types, valid values, and how to respond when data is invalid. Do not treat a successful cast as the criterion for business validity.

### 9.3. In-JVM Objects Differ from Data Sent Externally

| Context | What to Understand About the Payload |
| --- | --- |
| Creating `GenericMessage` in memory | The passed-in object is held by reference |
| Passing through internal steps of the example | No serialization step happens just from crossing a channel |
| Explicitly invoking a JSON transformer | Payload may change to a JSON string or structure |
| Sending via an adapter to a broker or HTTP | Data form depends on the adapter and converter |
| Persisting messages via an encoding store | Must satisfy the store's persistence and restoration contract |

A payload does not need to implement `Serializable` just to be wrapped in `GenericMessage`. When a storage or transport mechanism uses Java serialization, the involved objects must meet that mechanism's requirements. When using JSON or another format, satisfy the contract of the corresponding converter.

Internal headers may contain channel references or runtime objects. Those values do not inherently make sense in another JVM. Define schemas and header-mapping policies at boundaries rather than treating the entire internal envelope as an inter-system contract.

## 10. Common Errors When Equating Message with Java Objects

| Misunderstanding or Practice | Observable Consequence | How to Handle |
| --- | --- | --- |
| Mutating a DTO after sending while treating the message as an old snapshot | Consumers read the newly mutated value | Create snapshots or use immutable DTOs |
| Putting an `ArrayList` in a header and mutating it across branches | Other branches see unexpected data | Use immutable values or appropriate copies |
| `getHeaders().put(...)` | `UnsupportedOperationException` on standard headers | Build an output message with a builder |
| Using message ID as a stable order key | Correlation breaks when new messages are built | Use `orderId` or an operation key per contract |
| Assuming `OrderRequest` signature auto-decodes any JSON | Type mismatch or conversion failure | Configure mapping and data validation steps |
| Returning `null` from a transformer to drop a message | Transformation error instead of a clear filter result | Use a filter for keep/drop decisions |
| Building a message manually in a transformer while forgetting headers | Loses tracing or reply path | Specify required output headers explicitly |

In particular, synchronous errors in the illustrative flow typically propagate back to the `send` caller as a messaging exception, possibly wrapping the root cause. Setting the `errorChannel` header alone does not automatically route every synchronous exception to another flow. Error-reporting behavior for asynchronous tasks and pollers must be evaluated against the actual runtime configuration. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

When investigating, observe the actual payload type, business headers linking steps, the failing endpoint, and the root cause. There is no need to log the entire payload to see that a DTO was sent with the wrong type; in the order example, logging `orderId`, `operationId`, and the type name is usually enough to start tracing the flow.

## 11. Testing Important Properties

The tests below are hands-on exercises to place in a practice project. They verify shared data and the flow contract; having test code in the documentation does not imply it has been executed.

The test class uses the same package as `MessageObjectDemo` in section 8 and needs the `org.junit.jupiter:junit-jupiter` dependency in test scope.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class MessageObjectDemoTest {

    @Test
    void wrappingDoesNotCreatePayloadSnapshot() {
        List<String> ids = new ArrayList<>(List.of("ORD-1001"));
        Message<List<String>> message = new GenericMessage<>(ids);

        ids.add("ORD-1002");

        assertSame(ids, message.getPayload());
        assertEquals(
                List.of("ORD-1001", "ORD-1002"),
                message.getPayload()
        );
    }

    @Test
    void readOnlyHeadersCanStillContainMutableValues() {
        List<String> stages = new ArrayList<>();

        Message<String> message = MessageBuilder
                .withPayload("ORD-1001")
                .setHeader("stages", stages)
                .build();

        assertThrows(
                UnsupportedOperationException.class,
                () -> message.getHeaders().put("source", "WEB")
        );

        stages.add("RECEIVED");

        assertSame(stages, message.getHeaders().get("stages"));
        assertEquals(
                List.of("RECEIVED"),
                message.getHeaders().get("stages")
        );
    }

    @Test
    void flowChangesPayloadAndPreservesBusinessContext() {
        try (var context =
                     new AnnotationConfigApplicationContext(MessageObjectDemo.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);
            QueueChannel output =
                    context.getBean("orderOutput", QueueChannel.class);

            var original = new MessageObjectDemo.OrderRequest(
                    " ORD-1001 ",
                    new BigDecimal("125000")
            );

            Message<?> request = MessageBuilder
                    .withPayload(original)
                    .setHeader("source", "WEB")
                    .setHeader("operationId", "accept:ORD-1001")
                    .build();

            assertTrue(input.send(request));

            Message<?> reply = output.receive(1_000);
            assertNotNull(reply);

            var accepted = assertInstanceOf(
                    MessageObjectDemo.OrderAccepted.class,
                    reply.getPayload()
            );

            assertEquals("ORD-1001", accepted.orderId());
            assertEquals("ACCEPTED", accepted.status());
            assertEquals("WEB", reply.getHeaders().get("source"));
            assertEquals(
                    "accept:ORD-1001",
                    reply.getHeaders().get("operationId")
            );
            assertEquals(" ORD-1001 ", original.orderId());
        }
    }
}
~~~

The first test intentionally demonstrates an easily misunderstood case: wrapping a mutable collection does not create a snapshot. The second test separates two independent properties: the header map forbids modification while an object serving as a header value remains mutable. The third test observes real outcomes at the flow boundary, including payload type, normalized data, preserved headers, and the input object.

In a real application, add test cases for your specific contract: wrong input types, missing required headers, invalid data, or a converter failing to parse external data. When a flow has multiple branches or asynchronous processing, also test data isolation per the design.

## 12. Applying This When Developing Integration Patterns

Distinguishing objects from messages leads to concrete decisions:

- **Transformer:** produce an output payload representation suitable for the next step and specify which headers must travel along.
- **Router:** select a branch based on payload or headers explicitly defined in the contract.
- **Filter:** decide whether to keep or discard a message; avoid using a transformer's `null` value in place of a filtering policy.
- **Aggregator:** agree on group keys and input data; avoid mutating objects already handed to the grouping step.
- **Gateway:** let callers use a convenient Java interface while still designing the result-return path.
- **Error handling:** retain enough business identifiers and context to correlate failures back to the sent request.

For example, if an order is later split into multiple inventory-reservation requests, `orderId` may be shared business data, while the correlation key of the child messages must be designed to aggregate the right group. The Message ID of each individual message does not express that relationship by itself.

When writing a new step in a flow, determine four things: input payload type, output payload type, headers to preserve, and permission to mutate objects. Answering these four points clearly makes wiring endpoints and writing tests concrete, rather than relying only on the fact that methods accept an `Object`.
