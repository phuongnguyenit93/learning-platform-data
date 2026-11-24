# The Relationship Between Message, Command, Event, and Request

> Objective: distinguish the message envelope from the business intent it carries; recognize commands, events, requests, and replies; and apply these concepts when designing communication flows with Spring Messaging.

## 1. Four Concepts That Are Not at the Same Level

In system design, the words *message*, *command*, *event*, and *request* often appear side by side, yet they are not four peer data types.

- **Message** is the carrier that transports data across a communication boundary. It has a payload and may have headers describing metadata such as content type, correlation ID, origin, or routing information.
- **Command** expresses the intent to ask a component to perform an action, usually changing state.
- **Event** describes something that has happened and is meaningful to other components.
- **Request** is a query or proposal expecting a component to respond. Request–reply is an interaction pattern in which the sender expects a corresponding answer.

Therefore, a command, event, or request can be packaged inside a message. `Message<T>` describes how payload and metadata are carried; the payload type and communication contract express whether that message means a command, an event, or a request.

| Concept | Question It Answers | Typical Meaning | Expected Response |
|---|---|---|---|
| Message | How is data packaged and transported? | Payload plus headers | Depends on payload semantics and protocol |
| Command | What do we want the receiver to do? | Intent to perform an action | May have acknowledgement, result, or error |
| Event | What happened? | A business fact that has occurred | Usually needs no direct business result |
| Request | What is being asked or proposed? | Request for information or an outcome | Usually expects a reply in request–reply |

A common source of confusion is that "request" is sometimes used broadly to include requests to perform an action. When classifying messages in a message-driven architecture, separate clearly: a request to change state is a command; a request to read information is a query; request–reply describes how the sender waits for an outcome. An HTTP request is also a request at the protocol level, but that does not make every HTTP request a message in the message-broker sense.

## 2. Message Is the Envelope Carrying Payload and Headers

In Spring Messaging, `org.springframework.messaging.Message<T>` is the abstraction representing a message. It provides two main parts:

- **Payload:** the core data the consumer needs to process. The payload can be a Java object, a string, a byte array, or another type depending on the application.
- **Headers:** metadata accompanying the payload, such as content type, ID, timestamp, correlation ID, reply channel, or application-defined headers.

`MessageHeaders` provides standard headers; `MessageBuilder` helps construct a message without manually implementing the `Message<T>` interface. Example:

```java
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record ReserveInventory(String orderId, String sku, int quantity) {}
record OrderCreated(String orderId, Instant occurredAt) {}
record GetOrderStatus(String orderId) {}

public class MessageIntentDemo {
    public static void main(String[] args) {
        String correlationId = "corr-001";

        Message<ReserveInventory> commandMessage = MessageBuilder
                .withPayload(new ReserveInventory("ORD-100", "BOOK-01", 2))
                .setHeader("messageKind", "command")
                .build();

        Message<OrderCreated> eventMessage = MessageBuilder
                .withPayload(new OrderCreated("ORD-100",
                        Instant.parse("2026-11-07T00:00:00Z")))
                .setHeader("messageKind", "event")
                .build();

        Message<GetOrderStatus> requestMessage = MessageBuilder
                .withPayload(new GetOrderStatus("ORD-100"))
                .setHeader("messageKind", "request")
                .setHeader("correlationId", correlationId)
                .setHeader("replyTo", "orders.status.replies")
                .build();

        System.out.println(commandMessage.getPayload().getClass().getSimpleName());
        System.out.println(eventMessage.getPayload().getClass().getSimpleName());
        System.out.println(requestMessage.getPayload().getClass().getSimpleName());
        System.out.println(requestMessage.getHeaders().get("correlationId"));
        System.out.println(requestMessage.getHeaders().get("replyTo"));
    }
}
```

This snippet illustrates how messages are constructed, not a complete standalone application. The `correlationId` header is application-defined metadata used to link a request with its reply; Spring Messaging does not define a `MessageHeaders.CORRELATION_ID` constant. The `replyTo` header in the example is application-defined metadata; when integrating with a broker, how a reply address is represented must match the adapter and broker in use. Do not assume an arbitrary Java header automatically becomes a routing property in every broker.

The three variables above all share the outer type `Message<T>`, yet their payloads express three distinct meanings. Setting `messageKind` is only for illustration; in real systems, the payload type, destination name, and contract documentation usually convey the meaning already. Do not rely solely on a header string to drive business logic.

## 3. Command: Requesting an Action

A command expresses what the sender wants the system to do. Command names typically use imperative verbs or action phrases, such as `ReserveInventory`, `CancelOrder`, `ApprovePayment`.

Common characteristics:

- **Directed to a single responsible party:** a command is usually routed to one handler or a group of competing consumers so a single consumer processes it. Sending the same command to multiple independent handlers can cause the action to run multiple times.
- **May mutate state:** the handler may write to a database, reserve stock, create a payment, or update a workflow.
- **May be rejected:** invalid data, a disallowed business state, or unavailable resources can all cause a command to fail.
- **May produce a result:** the system may return an acceptance acknowledgement, a completion result, or an error. However, a command does not inherently require the caller to wait for the final outcome.

For example, `ReserveInventory` asks the inventory service to reserve two items for an order. The consumer must check stock quantities, order state, and reservation rules before updating data.

A command should describe intent, not a fact that has already happened. `CancelOrder` is a command because it requests cancellation; `OrderCancelled` is an event because it announces the order was successfully cancelled. Do not emit an `OrderCancelled` event merely because someone just submitted a cancellation request.

Because a command can be resent after a timeout or redelivery, handlers should incorporate idempotency. For instance, use a command ID or stable business key to detect duplicate processing while keeping duplicate checks and state updates within an appropriate transaction boundary.

## 4. Event: Announcing a Fact That Has Occurred

An event describes a business occurrence that has completed or been recorded. Event names typically use the past tense, such as `OrderCreated`, `PaymentAuthorized`, `InventoryReserved`.

Common characteristics:

- **Describes a fact:** an event states what happened, rather than instructing a consumer to perform a specific action.
- **Usually immutable in meaning:** once published, do not alter an old event to rewrite history. If new information arises, emit a new event or an appropriate event version.
- **Can have multiple subscribers:** billing, email, analytics, and shipping may all care about `OrderCreated` while performing their own tasks.
- **Producer is loosely coupled from consumers:** the event publisher does not need to know every existing subscriber or how they process it.
- **Does not inherently have a business reply:** a broker may confirm receipt or delivery of a message, but that does not mean all subscribers have finished their work.

For example, after an order is successfully created and saved, the system emits `OrderCreated`. The payment consumer may start payment authorization; the notification consumer may send an email; the analytics consumer may update metrics. These consumers react independently to the same fact.

A good event typically contains the business entity identifier, timestamp of occurrence, event identifier, and the data needed for consumers to understand the event. Avoid placing unnecessary sensitive data in the payload. If the payload can evolve over time, establish versioning and backwards-compatibility rules.

### How Does an Event Differ from a Command?

| Command | Event |
|---|---|
| "Reserve inventory for order ORD-100" | "Inventory for order ORD-100 has been reserved" |
| Expresses an intent to be processed | Expresses a fact that has occurred |
| Usually directed to one responsible handler | May interest multiple subscribers |
| Can be rejected before completion | Should not be emitted as fact if it did not happen |
| Name usually carries imperative meaning | Name is usually in the past tense |

## 5. Request: Asking or Proposing and Expecting a Reply

A request is a message or call for which the sender expects a corresponding reply. A request's content can be a question about data or a proposal to perform work. To avoid ambiguity in the business model, distinguish two cases:

- **Query request:** asks to read information, such as `GetOrderStatus`. Following CQRS/CQS principles, a query should not mutate business state.
- **Command request:** asks to perform an action, such as `ReserveInventory`. In business semantics, this is a command even if the protocol labels it a request.

Request–reply is an interaction pattern: the requester sends a request, and the receiver processes it and sends a reply. The reply may carry data, an outcome, a rejection, or an error. If the request travels over a message broker, both sides typically need:

1. **Correlation ID:** an identifier linking the reply to the original request.
2. **Reply destination:** where the requester receives replies, which may be a reply queue, topic, or channel depending on infrastructure.
3. **Timeout:** the maximum duration the requester waits for a result.
4. **Error rules:** distinguishing business rejections, technical errors, timeouts, and missing replies.
5. **Idempotency:** safe handling if the request is resent or received multiple times by the consumer.

For example, `GetOrderStatus` asks for the status of `ORD-100`. The reply might be `OrderStatusResult` containing status `SHIPPED`, or a not-found result. The requester uses the correlation ID to match each reply to its corresponding request, especially when multiple requests are in flight concurrently.

### Request–Reply Is Not Always Synchronous

With direct function calls or synchronous HTTP, the caller usually waits for the result within the same interaction thread. With messaging, request and reply can arrive at different times; the requester can await asynchronously, persist pending state, or continue other work. On timeout, the requester only knows no reply arrived in time; that does not prove the receiver never processed the request.

If you only need to know the broker accepted the message, an acknowledgement may suffice. If you need to know whether business work completed, you need a reply or a dedicated status lookup mechanism. **Transport acknowledgement does not equal business response.**

## 6. Relationship Between Concepts in a Business Flow

Consider an ordering workflow:

1. The client sends a `PlaceOrder` request to ask for an order to be created.
2. The application handles the request and may emit a `ReserveInventory` command to the inventory service.
3. The inventory service processes the command. On success, it emits an `InventoryReserved` event; otherwise, it returns a rejection or emits a failure message per contract.
4. Once the order is recorded, the system emits an `OrderCreated` event.
5. Email, billing, or analytics consumers receive the relevant events and execute their tasks.
6. The client can later send a `GetOrderStatus` query request to read the current status.

Each payload kind can be wrapped in a `Message<T>` when passing through Spring Messaging. However, not every step must use a broker. Client requests may arrive over HTTP; internal calls may be method calls; commands or events may travel through a message channel or a broker.

A simple diagram of business intent:

```text
Client
  | request: PlaceOrder
  v
Order Service
  | command: ReserveInventory
  v
Inventory Service
  | event: InventoryReserved
  v
Order workflow
  | event: OrderCreated
  +--------------------+
  v                    v
Email consumer      Analytics consumer

Client -- query request: GetOrderStatus --> Order Service
Client <-- reply: OrderStatusResult ----- Order Service
```

The diagram illustrates intent and processing flow. Concrete implementations may use HTTP, Spring Messaging, Spring Integration, JMS, or another broker.

## 7. Applying Spring Abstractions

Spring Messaging defines foundational abstractions for building message flows:

- `Message<T>` represents payload and headers.
- `MessageHeaders` provides standard and custom metadata.
- `MessageBuilder` creates messages.
- `MessageChannel` is the abstraction for a send target.
- `MessageHandler` is the abstraction for a message-handling component.

For example, a component can send a message through a `MessageChannel`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

class InventoryCommandSender {
    private final MessageChannel inventoryCommands;

    InventoryCommandSender(MessageChannel inventoryCommands) {
        this.inventoryCommands = inventoryCommands;
    }

    boolean send( Message<ReserveInventory> command ) {
        return inventoryCommands.send(command);
    }
}
```

This snippet only illustrates calling the `MessageChannel` API; creating the channel, wiring consumers, and configuring adapters depend on the application. Returning `true` indicates the send operation on the channel was accepted per that channel's contract. It does not prove inventory reservation succeeded.

`MessageChannel` is also not synonymous with a message broker. A channel can link components inside the same process; Spring Integration or Spring JMS adapters can bridge Spring flows to external messaging systems. Distinguish in-app abstractions from the underlying transport infrastructure.

### Spring Application Events and Messaging Events

Spring Framework also provides an application event mechanism with `ApplicationEventPublisher` and `@EventListener`. This allows beans within a Spring `ApplicationContext` to notify one another of events. By default, listeners run on the publishing thread; asynchronous handling requires appropriate configuration, such as `@Async` and an executor.

In-memory application events do not automatically become durable messages on a broker. They do not inherently offer persistence, redelivery after process restarts, or cross-application transmission. When inter-process communication or message durability is required, integrate appropriate messaging infrastructure.

## 8. Designing Payloads and Message Contracts

A clear message contract lets producers and consumers evolve more independently:

- **Name by intent:** `ReserveInventory` for commands, `InventoryReserved` for events, `GetOrderStatus` for query requests, and `OrderStatusResult` for replies.
- **Separate payload types:** avoid using one generic class with many optional fields and relying on a flag to guess the message kind.
- **Explicit identifiers:** consider message ID, command ID, event ID, correlation ID, and causation ID according to purpose. Message IDs and business IDs need not be identical.
- **Version management:** changes to fields, data types, or semantics must have a compatibility strategy across producers and consumers running different versions.
- **Send only necessary data:** do not assume consumers should access a producer's entire entity or internal data.
- **Authentication and authorization:** verify sender identity, permission to issue commands, and payload validity at trust boundaries.
- **Flow tracing:** use correlation IDs to link request/reply and trace context to follow steps across multiple processes.

For messages crossing a broker, Java payloads usually must be converted or serialized into a wire format such as JSON, XML, or byte arrays. `Message<T>` in Spring is an application-level abstraction; it does not prescribe a wire format or guarantee every Java object can be sent through every broker.

## 9. Common Pitfalls

- **Treating message and event as synonyms:** a message is a data carrier; an event is just one kind of meaning a payload can carry.
- **Emitting an event before the fact has actually occurred:** consumers may act on a fact that never took place. Only emit `OrderCreated` after the order has been recorded according to business rules.
- **Naming a command like an event:** `SendInvoice` is a request for action; `InvoiceSent` is a fact that happened.
- **Using an event to command a specific consumer:** if the producer needs a particular component to act, a command usually expresses intent more clearly.
- **Using a command like a broadcast event:** having multiple consumers process the same command can cause duplicate side effects. Choose the right destination and consumer pattern.
- **Treating a request timeout as unprocessed:** the receiver may have finished while the reply was delayed or lost. Design correlation, idempotency, and lookup mechanisms.
- **Confusing acknowledgements with business results:** a broker confirms a message was received or processed at the delivery layer; that does not necessarily mean the business request succeeded.
- **Ignoring duplicate messages:** commands and requests can be resent; consumers must be designed idempotently where appropriate.
- **Treating Spring application events as a message broker:** in-process `ApplicationContext` events do not automatically provide durability or network communication.
- **Stuffing too much data into payloads:** oversized payloads with unnecessary data increase transport cost, security exposure, and schema coupling.

## 10. How to Choose the Right Concept

When designing a communication flow, ask yourself:

1. What data is being transferred and what metadata is needed? That is a question about the **message envelope**.
2. Does the sender want a component to perform a state-changing action? Model it as a **command**.
3. Has a business fact occurred that multiple components may care about? Model it as an **event**.
4. Does the sender need to query data or wait for a corresponding result? Model it as a **query/request** and define the **reply** contract.
5. Is the result needed immediately in the calling flow or can it arrive later? The answer guides choosing a direct call, HTTP request–response, or messaging request–reply.
6. If messages are redelivered, processed multiple times, or arrive late, will the system remain correct? Design idempotency, timeouts, retries, and dead-letter handling accordingly.

## 11. Conclusion

A message is the envelope carrying a payload and headers. A command expresses intent to perform an action; an event records a fact that has happened; a request expresses a question or proposal and usually pairs with a reply in the request–reply pattern. A command, event, or request can all be represented as `Message<T>` in Spring Messaging.

When naming and designing contracts, clarify business intent first, then pick the transport mechanism. Properly distinguishing these concepts helps consumers know exactly what to do, reduces duplicate processing, avoids confusing delivery acknowledgements with business outcomes, and lets Spring components communicate intentionally.