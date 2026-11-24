# The Boundary Between Controller Completion and Client Receipt of Results

In a Spring application using WebSocket and STOMP, a controller method returning does not mean the client has received or processed the message. Between those two points lie multiple steps: Spring processes the return value, converts the payload, sends the message to the message broker, the broker looks up matching subscriptions, the server writes the STOMP frame onto the WebSocket connection, and the client processes the received frame.

When designing real-time APIs, name each milestone accurately. “The controller finished”, “the server published”, “the broker processed”, “the client received”, and “client-side business work completed” are distinct states.

## 1. Six Completion Milestones to Distinguish

| Milestone | What Has Happened | What Cannot Be Concluded Yet |
|---|---|---|
| Controller method returns | The method body finished running and produced a return value, or ended without returning a payload | The message converter succeeded; the broker received it; the client received it |
| Spring processes the return value | The return-value handler applies rules such as @SendTo, converts the payload into a message, and sends it to brokerChannel | All subscribers have received the message |
| Broker processes the message | The broker receives the message, finds matching subscriptions, and routes the message | The frame has reached the browser or the client has completed business processing |
| Server writes frame to connection | The message moves through clientOutboundChannel and the WebSocket transport writes the frame | The JavaScript callback has run or the UI has updated |
| Client receives STOMP MESSAGE | The client-side STOMP library received the frame and can invoke callbacks | Client-side business logic has persisted or completed the task |
| Client sends business acknowledgement | The client sends an acknowledgement message per the application contract; the server can record that acknowledgement | External side effects occurred exactly once, unless the application has proper idempotency and error controls |

The controller method usually controls only the business processing and return value directly. Subsequent steps belong to the messaging and transport pipeline, which can execute asynchronously across channels or executors.

## 2. Processing Flow from STOMP SEND to Client

Suppose a client sends a STOMP SEND to an application destination. Spring routes the message to a controller annotated with @MessageMapping. When the method returns, Spring continues processing that value according to the message-sending configuration.

~~~mermaid
sequenceDiagram
    participant C as STOMP client
    participant W as WebSocket transport
    participant I as clientInboundChannel
    participant H as @MessageMapping handler
    participant B as brokerChannel and broker
    participant O as clientOutboundChannel

    C->>W: SEND /app/orders.confirm
    W->>I: Decode frame and dispatch message
    I->>H: Invoke controller
    H-->>I: Return OrderConfirmed
    I->>B: Convert payload and publish /topic/orders
    B->>O: Route to active subscriptions
    O->>W: Send STOMP MESSAGE frame
    W-->>C: Frame arrives over WebSocket
    C->>C: Callback and application processing
~~~

Key components:

- **clientInboundChannel** receives messages from clients and dispatches them to Spring handlers or the broker.
- **SimpAnnotationMethodMessageHandler** locates the method matching @MessageMapping and invokes the controller.
- **Return-value handler** processes the return value. @SendTo or @SendToUser determines the destination; a message converter converts the payload into an appropriate message representation.
- **brokerChannel** carries application-sent messages to the message broker.
- **Message broker** manages subscriptions and routes messages to clients subscribed to the corresponding destination.
- **clientOutboundChannel** carries messages from the broker back to client connections.
- **WebSocket transport** writes frames to the connection. The browser's STOMP library decodes the frame and invokes the application callback.

If the message converter fails, the destination is invalid, or a channel rejects the send, the pipeline can fail after the controller body has already returned. Therefore, merely seeing a “controller completed” log is not enough to conclude the message was published.

## 3. Spring Framework Example

The following configuration uses application prefix /app, broker prefixes /topic and /queue, and WebSocket endpoint /ws.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

Controller receiving a command and returning a result sent to a topic.

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMessageController {

    @MessageMapping("/orders.confirm")
    @SendTo("/topic/orders")
    public OrderConfirmed confirm(ConfirmOrder command) {
        return new OrderConfirmed(command.orderId(), "CONFIRMED");
    }

    public record ConfirmOrder(String orderId) {}

    public record OrderConfirmed(String orderId, String status) {}
}
~~~

With the configuration above:

1. The client sends a command to /app/orders.confirm.
2. Spring invokes confirm.
3. The method returns OrderConfirmed.
4. Spring converts the object into a message and sends it to /topic/orders.
5. The broker routes the message to clients subscribed to /topic/orders.

@SendTo("/topic/orders") sends to a shared destination. Any active subscriber on that destination can receive the message; this is not a private reply to the client that sent the command. If you need to send to a specific user, you can use @SendToUser or SimpMessagingTemplate.convertAndSendToUser(...).

The client subscribes to receive messages using a STOMP library, such as @stomp/stompjs:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000,
});

client.onConnect = () => {
  client.subscribe("/topic/orders", (frame) => {
    const event = JSON.parse(frame.body);
    console.log("Client received:", event);
  });
};

client.activate();
~~~

The callback above runs only when the STOMP library receives a MESSAGE frame. If the callback goes on to call an API, update IndexedDB, or mutate UI state, those operations can still fail separately. Define clearly whether the application treats “received” or “processing finished” as the completion milestone.

## 4. What Do @SendTo, the Broker, and STOMP Acknowledgements Mean?

### @SendTo Is Not a Delivery Acknowledgement

@SendTo only declares the destination for a handler's return value. This annotation does not instruct Spring to wait for all subscribers to confirm message receipt. Nor does it turn a message publish into a request-response call with end-to-end delivery guarantees.

Similarly, calling SimpMessagingTemplate.convertAndSend(...) expresses intent to submit a message into the messaging infrastructure. The return of that call does not prove the browser has processed the payload.

### STOMP RECEIPT

A STOMP frame can carry a receipt header. If the broker supports receipts, the server sends a RECEIPT frame to indicate the corresponding frame was processed under the broker's contract. A receipt for SEND does not prove every subscriber received the MESSAGE, let alone that business code in the browser executed.

### STOMP ACK

For subscriptions using an acknowledgement mode supported by the broker, a client can send an ACK frame after receiving a MESSAGE. This is an acknowledgement at the STOMP/broker layer. It does not automatically prove that a business transaction in the application committed or that an external side effect completed.

Spring's Simple Broker supports only a subset of STOMP and does not provide advanced features such as ACK, RECEIPT, or durable subscriptions. Do not assume these mechanisms work when configuring with enableSimpleBroker(...). If those features are required, choose an appropriate broker and configure and test the exact capabilities of the broker in use.

### Application-Level Business Acknowledgements

If the requirement is knowing that the client has processed an event, define a dedicated acknowledgement message. For instance, the client sends the event ID back to an application destination after finishing the prescribed processing step:

- The client receives an event carrying an eventId.
- The client performs processing and persists the required state.
- The client sends a business ACK including the eventId.
- The server authenticates the sender, validates the event, and records the acknowledged state.
- The server can retry pending events; the client must handle duplicates safely using an idempotency key.

A business ACK is only as accurate as the moment the client sends it. If the client sends the ACK before saving results or completing side effects, the server can record a premature confirmation. Define clearly whether the ACK means “received”, “UI updated”, or “business result persisted”.

## 5. Limitations of WebSocket and Message Brokers

WebSocket provides a full-duplex connection and ordered frame delivery over an active connection. That does not guarantee that a message will be stored and delivered to a client after a disconnection.

With Spring's Simple Broker:

- Subscriptions are managed in application memory.
- Messages are routed to subscribers active at the moment the broker processes them.
- Disconnected clients can miss messages published while offline.
- Reconnecting does not automatically replay missed messages.
- Simple Broker is not a durable message broker and is unsuitable for requirements needing persistence, replay, or clustering.

When using a broker relay with an external broker, persistence, durable subscriptions, acknowledgements, and retries depend on the broker, destination type, and subscription configuration. Enabling a broker relay alone does not automatically create end-to-end delivery guarantees.

If an important event must be visible to the client after reconnecting, store the state or event in durable storage. The client can resynchronize via REST/API or request replay by event ID, sequence, or cursor. WebSocket should act as a fast notification channel, while durable data must have a queryable source of truth.

## 6. Transaction Boundaries and Publishing Timing

A common bug is sending an “order confirmed” notification before the transaction writing the order commits. The client may receive the notification and query the data while the transaction is still uncommitted or later rolls back.

For example, calling SimpMessagingTemplate.convertAndSend(...) directly inside a method with an open transaction can publish the message before the transaction commits. When a notification is valid only after commit, emit the event post-commit, such as with @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT), or use a transactional outbox if higher reliability is needed.

A transactional outbox stores the business change and the event record in the same transaction. A separate process reads the outbox and publishes the event; events not yet sent successfully can be retried. Because retries can produce duplicate deliveries, consumers still need idempotency.

## 7. Designing Verifiable Delivery

If the application only needs ephemeral UI updates, publishing to a topic and handling callbacks may be enough. If business requirements demand knowing the client received or processed the message, design these additional mechanisms:

1. **Event identity:** Give each event a unique eventId, correlationId, creation timestamp, and business entity ID. Never use payload content as an identifier.
2. **Persist required state:** Store the event or business state in a database before asking the client to act. Never rely on a single WebSocket message as data storage.
3. **Contractual ACK:** The client sends a business ACK immediately after the required milestone. The server verifies event ownership and persists the ACK.
4. **Bounded retries:** The server retries unacknowledged events according to timeout and retry-count policies. Exhausted retries must enter an inspectable operational state.
5. **Idempotency:** Both client and server handle duplicate events safely. Receiving the same eventId again must not cause unintended extra side effects.
6. **Recovery after reconnect:** The client re-establishes subscriptions and then synchronizes missed events or state from durable storage.
7. **Stage-by-stage observability:** Log the same eventId when the controller completes, at publish time, when the broker routes if observable, when the client receives it, and when the business ACK is saved. Never log full sensitive payloads.

Avoid using a single log such as “sent successfully” for every stage. Name events to reflect accurately what actually happened, such as controller_completed, message_published, client_message_received, and business_ack_recorded.

## 8. Testing the Exact Boundary You Need to Guarantee

- **Controller unit tests:** Verify business logic and return values. This test does not prove the message reached any client.
- **Message handler tests:** Verify destinations, message conversion, and that Spring forwards the message into the broker channel.
- **STOMP/WebSocket integration tests:** Use a real STOMP client to connect to the endpoint, subscribe to the destination, send commands, and wait for messages with a bounded timeout. This verifies the path through the messaging infrastructure in a test environment.
- **Disconnect tests:** Drop the connection mid-publish, reconnect, and verify the replay or resynchronization behavior the application commits to.
- **ACK and retry tests:** Verify valid ACKs, invalid event ACKs, duplicate ACKs, missing ACKs from clients, and event redelivery.
- **Transaction tests:** Verify an event is not published as a committed change when the transaction rolls back.

Avoid using fixed Thread.sleep(...) calls to conclude a message arrived. Wait on an explicit condition using a latch, future, or timeout-bounded assertion; this keeps tests stable and clarifies which milestone is being verified.

## 9. Checklist When Reading Logs or Debugging Errors

- Was the controller actually invoked and did it return the expected payload?
- Did the return-value handler or SimpMessagingTemplate convert and publish the message successfully?
- Does the destination have the right prefix and match what the client subscribed to?
- Is the active broker Simple Broker or a broker relay? Which STOMP features does it support?
- Was the client connected, subscribed to the right destination, and still connected at publish time?
- Did the message callback execute? If it did, did payload handling or UI updating fail?
- If business confirmation is required, was the ACK sent and did the server persist the ACK?
- If the client went offline, does the application have a durable data source to resynchronize?

When reporting “the controller completed but the client did not see the result”, identify the first stage lacking evidence of success. Separating these milestones pinpoints failures among the controller, message converter, channel, broker, WebSocket transport, and client code without mistaking a publish for completed business processing.