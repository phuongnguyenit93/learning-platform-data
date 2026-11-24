# Designing Commands, Events, and Responses by Business Responsibility

## 1. Why Must We Distinguish Three Types of Messages?

In a messaging-driven system, a message may request an action, announce a fact that has occurred, or reply to a previous request. These three purposes give rise to three distinct contracts:

- A **Command** expresses the intent for an authoritative component to perform a business action.
- An **Event** records a business occurrence that has already happened so interested components can react.
- A **Response** returns the result to the party that sent a request or command.

Distinguishing them properly helps clarify who is responsible for handling, who is allowed to mutate state, who needs to receive the information, and the degree of coupling between components. A class name is merely a hint; the business meaning and how the message is used determine the contract type.

Example in an order placement workflow:

1. The user sends a `PlaceOrder` command to request placing an order.
2. The order management component validates the rules, persists the order, and emits an `OrderPlaced` event once order placement is confirmed.
3. The sender receives a `PlaceOrderResult` response indicating whether the request has completed, was rejected, or has only been accepted.
4. Other components receive `OrderPlaced` to update inventory, generate an invoice, send notifications, or update reports.

`PlaceOrder`, `OrderPlaced`, and `PlaceOrderResult` may contain some of the same data, but they answer three different questions: "please do this", "this has happened", and "what was the outcome of your request?".

## 2. Command: Requesting a Business Action

### 2.1. Nature and Responsibility

A command is an imperative message. The sender wants an authoritative component to perform an action that changes state or produces a business decision.

Examples:

- `PlaceOrder`: place an order.
- `CancelOrder`: cancel an order.
- `ReserveInventory`: reserve inventory items.
- `ChangeDeliveryAddress`: change the delivery address.
- `ApproveRefund`: approve a refund.

Command names typically use imperative verbs. A command should describe business intent, not storage operations such as `UpdateOrderTable` or `SetStatusTo2`.

A command typically has the following characteristics:

- It has a clearly defined authoritative handler. For example, the Order Service is responsible for deciding whether an order can be placed or cancelled.
- It can be rejected due to invalid data, insufficient permissions, the current state, or business rules.
- It is validated before mutating state.
- It may require a unique identifier to prevent duplicate processing when the sender retries.
- It may return a response so the sender knows the outcome or acceptance status.

A command is a request, not proof that the action succeeded. Sending `PlaceOrder` does not mean the order has been placed. Only after the component owning the business domain confirms and commits the change can the system publish the corresponding fact, such as `OrderPlaced`.

### 2.2. Designing the Command Payload

The payload should contain the data needed to evaluate and execute the intent. Example:

~~~java
import java.util.List;
import java.util.UUID;

public record OrderLine(String productId, int quantity) {}

public record PlaceOrder(
    UUID commandId,
    UUID customerId,
    List<OrderLine> lines,
    String idempotencyKey
) {}
~~~

`commandId` identifies the command submission; `idempotencyKey` can be used to detect retries of the same intent. Both fields can be merged if the system already has a single unique identification convention, but the deduplication semantics must be clearly defined.

The Java snippets in this lesson illustrate contracts and Spring integration. The remaining domain types, services, and transport configurations belong to the specific application, so the controller snippets are not standalone runnable programs as-is.

A good command should:

1. Express a business intent that can be understood independently.
2. Carry enough data for the handler to check permissions and business rules.
3. Avoid sending an entire entity or persistence object merely for serialization convenience.
4. Not ask the client to decide fields that the domain owner must compute, such as the final total, allowed status, or ownership.
5. Have clear rules for retries, timeouts, and duplicate handling.

If data version checking is needed before making changes, an `expectedVersion` or equivalent condition can be sent. The handler uses that condition to detect concurrent updates; it should not trust a client-declared state without verifying it at the domain owner.

### 2.3. Who Should Handle a Command?

A command should be routed to the component responsible for the requested behavior. For example, `ReserveInventory` must be sent to the component owning inventory rules. The caller should not mutate inventory data directly by writing into another service's database.

A command may trigger multiple internal steps or a workflow, but decision-making responsibility must remain clear. If a long-running process requires multiple services to coordinate, a process manager or saga can be used to orchestrate subsequent commands and track outcome events.

## 3. Event: Announcing a Business Fact That Has Occurred

### 3.1. Nature and Responsibility

An event is a record of a fact that has occurred in the business domain. An event does not tell a consumer to perform a specific action, nor is it a request to mutate state.

Examples:

- `OrderPlaced`: the order has been placed.
- `OrderCancelled`: the order has been cancelled.
- `InventoryReserved`: the inventory has been reserved.
- `PaymentCaptured`: the payment has been captured.
- `AddressChanged`: the address has been changed.

Event names typically use the past tense or express a state that has already occurred. If the command is `CancelOrder`, the corresponding event may be `OrderCancelled`.

Events typically have the following characteristics:

- Created by the component that owns the business fact.
- Emitted only after the corresponding occurrence has actually happened.
- Treated as immutable once published; if a subsequent occurrence happens, emit a new event.
- May have multiple independent consumers.
- Consumers can react differently without the producer needing to know who each consumer is.
- May be stored, replayed, or processed asynchronously depending on the architecture.

For example, after the Order Service emits `OrderPlaced`, the Inventory Service can reserve stock, the Notification Service can send an email, and the Analytics Service can update reports. The producer does not need to call each service directly to tell them to do their work.

### 3.2. An Event Is Not a Broadcast Command

Do not emit a `PleaseReserveInventory` event if the actual intent is to ask the Inventory Service to reserve stock. That is a command and requires a handler responsible for deciding whether it can be executed.

Events should express outcomes: `InventoryReserved` or `InventoryReservationRejected`. A consumer can use that fact to update its state or issue another command if needed.

The key distinction is decision-making authority:

- With a command, the sender requests an action; the receiver may accept or reject it.
- With an event, the producer announces a fact it is responsible for confirming; the consumer decides the appropriate reaction within its own scope.

### 3.3. Designing the Event Payload

Example order event:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    UUID customerId,
    Instant occurredAt,
    long aggregateVersion,
    String correlationId
) {}
~~~

Commonly useful fields:

| Field | Purpose |
|---|---|
| `eventId` | Unique identifier so consumers can detect already-processed messages |
| `occurredAt` | Timestamp when the fact occurred according to the system's time convention |
| `aggregateId` | Identifier of the related business object |
| `aggregateVersion` | Version or sequence order of the aggregate's changes |
| `correlationId` | Links the event to the originating request or workflow |
| `causationId` | Identifier of the command/event that directly caused the current event |
| `schemaVersion` | Contract structure version to support schema evolution |

Not every event needs every field. Only add metadata that has real operational or business value. Do not include passwords, access tokens, secrets, or entire customer profiles in an event just to spare consumers from querying.

### 3.4. Events and Immutability

Once `OrderPlaced` has been published, do not mutate the old event into `OrderCancelled`. Cancelling an order is a new fact and must be represented by a new event.

If an older payload lacks information, consider adding compatible fields, emitting a new event version, or building an appropriate projection. Changing the meaning of an already-published field can break existing consumers and historical data.

## 4. Response: Outcome for the Request Sender

### 4.1. Nature and Responsibility

A response is a message replying to a request or command. It is typically linked to the original request via a correlation ID, request ID, or the protocol's request-response mechanism.

Examples:

- `PlaceOrderResult`: outcome of the place-order command.
- `GetOrderResult`: data returned from an order query.
- `ReserveInventoryResult`: outcome of the inventory reservation request.

A response answers the sender: was the request completed, rejected, or merely accepted? It may contain data the caller needs to continue its workflow.

Example:

~~~java
import java.util.UUID;

public record PlaceOrderResult(
    UUID commandId,
    UUID orderId,
    Status status,
    String rejectionCode
) {
    public enum Status {
        ACCEPTED,
        COMPLETED,
        REJECTED
    }
}
~~~

Statuses must have clear semantics:

- `ACCEPTED`: the system has accepted responsibility for processing; work may still be in progress.
- `COMPLETED`: the business action has finished according to the API's guarantee.
- `REJECTED`: the request was rejected due to business or data reasons.

Do not use `ACCEPTED` as if the work were already finished. If a command is processed asynchronously, the response can return `ACCEPTED` along with a command ID or operation ID; the final outcome is communicated via an event or a status query endpoint.

### 4.2. A Response Is Not an Event

`PlaceOrderResult` is a response intended for the caller of `PlaceOrder`. `OrderPlaced` is a fact intended for any consumer interested in knowing that an order has been placed.

The two messages may be created close together, but they do not replace each other:

- A response has a direct relationship to a request and is typically sent back to the specific caller.
- An event can be delivered to multiple consumers without requiring the original caller to remain connected.
- A response can say `REJECTED`; the `OrderPlaced` event is emitted only when the order has actually been placed.
- Event consumers should not depend on a single client's private response.

An event should not be used as a response merely because both contain `orderId`. Conversely, a response does not replace an event if other services need to know that a business state change has occurred.

### 4.3. Business Errors and Technical Errors

We should distinguish:

- **Business rejection:** for example, the customer is ineligible or the order cannot be cancelled in its current state. A response with status `REJECTED` and a stable reason code can be returned.
- **Authentication/authorization errors:** the caller is not permitted to execute the command. Handle according to the transport/API's security and error mechanisms.
- **Transient technical errors:** the broker is unavailable, timeout, or dependency failure. Can be retried according to policy, but idempotency must be guaranteed.
- **Protocol/serialization errors:** the payload cannot be decoded or the message violates the contract; must be logged and handled according to the transport's error mechanism.

A timeout does not prove the command failed. The server may have already committed while the response was lost in transit. When retrying, use the same idempotency key or query the status by command ID to avoid executing the action twice.

## 5. Comparing the Three Contract Types

| Criterion | Command | Event | Response |
|---|---|---|---|
| Meaning | Request an action | Fact that has occurred | Outcome of a request |
| Naming style | Imperative verb | Occurrence in past/completed form | Outcome or result name |
| Creator | Caller or orchestrating component | Component owning the fact | Request handler |
| Receiver | One authoritative owner/handler | One or more consumers | Request caller |
| Can be rejected? | Yes | Not a request to be rejected | Can represent a rejection outcome |
| State change | Goal of the command | Records a change that already happened | Does not by itself signify a change |
| Request relation | Is the request/intent | Independent of any specific caller | Tied to the original request |
| Example | `PlaceOrder` | `OrderPlaced` | `PlaceOrderResult` |

Three questions can be used to classify a message:

1. What does the sender want the receiver to do? That is usually a command.
2. What fact is the message announcing as having occurred? That is usually an event.
3. Which request is the message answering and what is the outcome? That is usually a response.

If it is not yet clear which type a message belongs to, clarify the owner of the behavior, the meaning of the message, and who needs to receive it before choosing a class name or destination.

## 6. Designing a Complete Business Workflow

### 6.1. Synchronous Order Placement Flow

Suppose an application handles order placement within a request-response interaction:

~~~text
Client
  |
  | PlaceOrder (command)
  v
Order Service
  |-- validate data and permissions
  |-- validate business rules
  |-- persist order
  |-- write OrderPlaced to outbox in the same transaction
  |
  | PlaceOrderResult (response)
  v
Client

Outbox relay
  |
  | OrderPlaced (event)
  +------> Inventory Service
  +------> Notification Service
  +------> Analytics Service
~~~

Order Service is the owner of the order placement decision. It returns `COMPLETED` only after the transaction containing the business changes has committed in accordance with the application's guarantees. The `OrderPlaced` event is published to consumers via the outbox relay.

The response does not need to wait for emails or reports to finish if those tasks are independent asynchronous reactions. If the business requires inventory to be reserved successfully before confirming order placement, the workflow must express that condition explicitly; never emit `OrderPlaced` early and assume every consumer will succeed.

### 6.2. Asynchronous Processing Flow

For long-running tasks, the caller may receive an `ACCEPTED` response along with an operation ID. Then:

1. The handler records the command and its processing status.
2. A worker executes the workflow.
3. When a result is reached, the service emits an event such as `OrderPlaced` or `OrderPlacementFailed`.
4. The caller tracks progress via a subscription, callback, or status query endpoint.

You must specify the status retention period, retry policy, how to look up the operation ID, and which event represents the final outcome. Do not let clients infer that `ACCEPTED` means the business operation has completed.

### 6.3. When to Use Request-Response, Fire-and-Forget, or Events?

- Use request-response when the caller needs the outcome to proceed and can accept the temporal coupling of a request.
- Use an asynchronous command when the caller only needs to know the system has accepted the request, while the result arrives later.
- Use an event when a fact needs to be distributed to interested components and the producer does not need to wait for each consumer to reply.
- Use a query when the sole purpose is reading data; avoid naming a query like a state-mutating command.

Do not choose an event merely to avoid designing a response. If the caller needs to know whether a command was accepted, provide an appropriate acknowledgement or response.

## 7. Metadata, Correlation, and Message Routing

### 7.1. Payload and Envelope

In Spring Messaging, `Message<T>` is an envelope containing a payload and headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<PlaceOrder> message = MessageBuilder
    .withPayload(command)
    .setHeader("correlationId", correlationId)
    .setHeader("tenantId", tenantId)
    .build();
~~~

The payload describes the business content. Headers carry metadata for routing, correlation, tracing, tenant identification, or operational purposes. Do not move every business field into headers; consumers need a clear payload contract to understand the message.

`MessageHeaders` is Spring's header structure. Build messages via `MessageBuilder` instead of mutating the header map directly after the message has been constructed. Whether a header is propagated across a transport depends on the adapter and protocol configuration; do not assume every internal header automatically crosses the network.

### 7.2. IDs to Distinguish

| ID | Role |
|---|---|
| `messageId` | Identifies a specific message |
| `commandId` | Identifies a business request |
| `eventId` | Identifies an emitted fact |
| `correlationId` | Links messages belonging to the same request or workflow |
| `causationId` | Indicates the message that directly caused the current message |
| `aggregateId` | Identifies the related business object |

You do not need to create a separate ID for every purpose if one ID can serve multiple roles, but you must keep semantics consistent. For example, retries of the same command typically keep the same idempotency key/command ID; each emitted event is a distinct message with its own event ID.

### 7.3. Routing Rules

Route commands to the authoritative owner. Route events to topics or subscriptions of interested consumers. Responses must be correlated with the request and returned to the right caller or designated destination.

Do not rely on destination names as a substitute for authentication and authorization. Tenant, user, or role headers sent by a client can be spoofed; they must be verified using trusted server-side security mechanisms.

## 8. Applying with Spring Framework Messaging

### 8.1. Message and MessageChannel

Spring Messaging provides the `Message<T>` abstraction to encapsulate payload and headers, along with channel abstractions to send messages between components. API-level example:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean sent = commandChannel.send(
    MessageBuilder.withPayload(command)
        .setHeader("correlationId", correlationId)
        .build()
);
~~~

`sent` indicates whether sending into the channel succeeded according to the channel's contract. It does not prove that the command has been processed or the business transaction has committed. The business outcome must be confirmed through an appropriate response, status, or event.

### 8.2. RSocket: Commands and Responses via Request-Response

Spring supports RSocket routing via `@MessageMapping`. A controller can receive a command and return a `Mono` containing the response:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    private final OrderApplicationService orderService;

    public OrderRSocketController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.place")
    public Mono<PlaceOrderResult> place(PlaceOrder command) {
        return orderService.place(command);
    }
}
~~~

The caller sends the command and receives the response using `RSocketRequester`:

~~~java
Mono<PlaceOrderResult> result = requester
    .route("orders.place")
    .data(command)
    .retrieveMono(PlaceOrderResult.class);
~~~

In this example, `orders.place` is the command route. `PlaceOrderResult` is the corresponding response. Returning a `Mono` from the handler enables asynchronous processing with Reactor; it does not turn the response into an event.

### 8.3. STOMP: Separating Replies and Event Topics

With STOMP, clients can send commands to destinations managed by `@MessageMapping`. To return a response to a specific user, use an appropriate reply destination, such as `@SendToUser`:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class OrderStompController {

    private final OrderApplicationService orderService;

    public OrderStompController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.place")
    @SendToUser("/queue/order-results")
    public PlaceOrderResult place(PlaceOrder command) {
        return orderService.placeSynchronously(command);
    }
}
~~~

When an event needs to be distributed to multiple subscribers, the application can use `SimpMessagingTemplate` to send the event to a topic:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;

public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderPlaced event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

Here `/queue/order-results` is the per-user response destination, while `/topic/orders` is the event distribution destination. Broker configuration, application destination prefixes, and destination security must align with the application's STOMP configuration.

`@MessageMapping` is a Spring Messaging annotation; the exact routing and response mechanism depends on the transport. RSocket routes and STOMP destinations should not be treated as the same protocol merely because they share the same annotation.

### 8.4. Application Events and Messages Sent via a Broker

`ApplicationEventPublisher` publishes events within the scope of a Spring ApplicationContext. It is useful for communication between beans in the same application, but by itself it is not a mechanism for sending events through a broker to other services.

If an event must cross process or service boundaries, use an appropriate integration/broker or a reliable message publishing mechanism. `@TransactionalEventListener` can be used to react after commit for internal events; however, a post-commit listener does not by itself provide durability guarantees if the process stops before publishing to the broker.

## 9. Ensuring Reliability When Sending Commands and Events

### 9.1. Idempotency and Duplicate Handling

Messages may be redelivered due to timeouts, retries, or broker delivery semantics. Therefore, command handlers and event consumers need an idempotency strategy.

For commands:

- Store the idempotency key/command ID along with the processing outcome.
- If the same key is received again, return the known result instead of applying the change a second time.
- Define the uniqueness scope of the key, for example by tenant and command type.
- Do not delete deduplication records before the supported retry window expires.

For events:

- Use the event ID to identify already-processed events.
- Record processing and update consumer data in the same transaction whenever possible.
- If an old or duplicate event is received, do not apply side effects again.

Do not assume a distributed system always delivers exactly once. Idempotent design is generally more practical than relying on an end-to-end exactly-once promise across multiple systems.

### 9.2. Transactional Outbox

A common failure mode is updating the database successfully while publishing the event fails, or publishing the event successfully while the business transaction rolls back. Because these two actions occur in two different systems, they are not automatically atomic.

The transactional outbox solves this by writing the business data and an outbox record in the same database transaction:

1. The handler validates the command and updates the aggregate.
2. In the same transaction, write the event to be emitted into an outbox table.
3. After commit, a relay reads the outbox and publishes to the broker.
4. The relay marks entries as sent or continues retrying on failure.
5. Consumers process idempotently because the relay may republish after a crash.

The outbox prevents losing the intent to emit an event between business commit and publish, but you still need to manage retries, duplicates, ordering, and cleanup of sent records.

### 9.3. Ordering and Versioning

If events for the same aggregate must be processed in order, include an aggregate version or sequence number and use an appropriate broker partition key. Do not assume global ordering across partitions or across consumers.

Consumers can:

- Detect duplicate events using the event ID.
- Detect gaps or out-of-order events using the aggregate version.
- Ignore stale events that have already been applied.
- Retry or buffer early events until the preceding version has been processed.

Require ordering only within the business scope that truly needs it; global ordering usually limits scalability.

### 9.4. Contract Evolution

Commands, events, and responses are all APIs between components. When changing them:

- Prefer adding optional fields with sensible defaults.
- Do not change the meaning of existing fields.
- Do not reuse an event name for a different fact.
- Have clear schema versions or compatibility rules.
- Test against existing consumers before releasing changes.
- Preserve the ability to read historical messages if the system requires replay.

Events typically outlive short-lived request-response interactions because they can be stored and replayed. Therefore, be especially careful with event schemas and sensitive data.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Naming a command in the past tense like `OrderPlaced` | Unclear whether it is a request or a fact | Use `PlaceOrder` for the command |
| Using an event `PleaseSendEmail` to request an action | Consumers become command handlers with unclear authority | Send a command to the authoritative service or emit an actual fact |
| Using a response as an event for all services | Consumers become coupled to the caller's lifecycle | Emit an independent event after the fact occurs |
| Publishing an event before the transaction commits | Consumers observe uncommitted data | Use an outbox or a reliable post-commit publishing mechanism |
| Repeated command calls create duplicate orders | Retries cause repeated side effects | Use an idempotency key and persist the processing outcome |
| Returning `ACCEPTED` while clients treat it as completed | Workflow state is misinterpreted | Clearly define accepted/completed/rejected |
| Stuffing an entire database entity into the payload | Contract is tightly coupled to internal schema | Design DTOs based on business needs |
| Putting secrets into events | Increases data exposure scope and is hard to revoke | Minimize payloads and enforce access controls |
| Using one event for multiple different meanings | Consumers do not know how to interpret it | Each event should describe one clear fact |
| Treating a successful channel send as business success | Callers receive false confirmation | Distinguish send acknowledgement from business response |

## 11. Message Contract Design Process

When starting a new feature, you can follow this sequence:

1. **Describe the business behavior:** what does the user or service want to happen?
2. **Identify the owner:** which component is responsible for making decisions and mutating state?
3. **Define the command:** intent-based name, required payload, permissions, validation, idempotency, and retry rules.
4. **Define the outcome:** does the caller need to know if it was accepted, completed, or rejected? What data is needed in the response?
5. **Define the events:** what facts have actually occurred and which components might care?
6. **Choose when to emit events:** should the event correspond to a committed change or a specific workflow milestone?
7. **Define metadata:** which message ID, correlation ID, causation ID, aggregate ID, and version are genuinely needed?
8. **Choose protocol and destinations:** request-response, stream, queue, or topic; who sends, who receives, and who has permissions?
9. **Design error handling and reliability:** duplicates, timeouts, retries, outbox, ordering, dead-lettering, and replay.
10. **Verify compatibility:** can existing consumers read the new payload? Is versioning or migration needed?

## 12. Testing Contracts and Processing Flows

Both message semantics and handler behavior should be tested:

- **Command unit tests:** valid data, invalid data, insufficient permissions, disallowed states, and duplicate commands.
- **Response tests:** proper correlation, meaningful statuses, stable rejection codes, and never returning `COMPLETED` before commit.
- **Event tests:** emit events only when the fact occurs; verify payload and aggregate version are accurate.
- **Outbox integration tests:** rolled-back transactions do not produce emitted events; relay retries do not lose events.
- **Consumer tests:** safe duplicate handling, out-of-version events handled per policy, and non-repeating side effects.
- **Contract tests:** producer and consumer remain compatible when adding fields or changing schemas.
- **Transport integration tests:** correct routes/destinations, proper authentication/authorization, and errors mapped according to convention.

When debugging, log message ID, command/event ID, correlation ID, aggregate ID, and route/destination at an appropriate level. Avoid logging full payloads if they contain personal or secret data.

## 13. References

- [Spring Framework Reference — Messaging flow and abstractions](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): the `Message`, `MessageChannel`, and `MessageHandler` abstractions and message flow in Spring.
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): request-response, routing, annotated responders, and `RSocketRequester`.
- [Spring Framework Reference — STOMP annotated controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): `@MessageMapping`, `@SendToUser`, and return value handling.
- [Spring Framework Javadoc — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html): payload and headers of a Spring Message.
- [Spring Framework Javadoc — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html): building messages and setting headers.
- [Spring Framework Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): listening to application events by transaction phase.
