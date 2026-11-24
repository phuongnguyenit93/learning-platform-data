# SEND, SUBSCRIBE, UNSUBSCRIBE, and MESSAGE in STOMP

## Objectives

After this lesson, you can:

- Describe the structure of a STOMP frame consisting of a command, headers, a body, and a terminating byte.
- Distinguish SEND, SUBSCRIBE, and UNSUBSCRIBE as frames the client sends, and MESSAGE as a frame the server sends.
- Identify the required and optional headers according to STOMP 1.2.
- Track a subscription by its id and understand the acknowledgement modes.
- Distinguish message-id from the ack token used in ACK/NACK.
- Understand what a receipt confirms and what it does not confirm.
- Apply the frames in Spring STOMP over WebSocket with @MessageMapping, @SendTo, and a broker.
- Avoid confusing a broker's destination conventions with the general rules of STOMP.

## 1. Structure of a STOMP frame

STOMP (Simple Text Oriented Messaging Protocol) is a frame-based message transport protocol. It runs over a reliable bidirectional streaming connection such as TCP or WebSocket. Even though the protocol name contains the word Text, the body can still contain binary data.

General structure:

~~~text
COMMAND
header-name:header-value
another-header:another-value

message body^@
~~~

A frame consists of:

1. **Command:** a command name such as SEND, SUBSCRIBE, UNSUBSCRIBE, or MESSAGE.
2. **Headers:** key:value lines; each line ends with an EOL.
3. **Blank line:** marks the end of the headers and the start of the body.
4. **Body:** the message content, if the command allows a body.
5. **NULL octet:** a byte with the value 0, which terminates the frame.

In the example, ^@ represents the NULL byte (0x00). In real transmission, the client must send the NULL byte, not the two characters caret and @.

STOMP 1.2 allows the EOL to be LF or CRLF. Command and header names are case-sensitive: SEND differs from send; content-type differs from Content-Type.

### Body and content headers

According to STOMP 1.2, only SEND, MESSAGE, and ERROR are allowed to have a body. SUBSCRIBE and UNSUBSCRIBE have no body.

Two commonly used headers:

- content-type: a MIME type describing the body, for example text/plain or application/json.
- content-length: the length of the body in octets/bytes, not the number of Unicode characters.

If the body has a NULL byte in the middle, the frame must have content-length so that the parser knows where the body ends. For an ordinary body, the specification recommends sending content-type and content-length when appropriate. STOMP supports UTF-8 by default.

## 2. The roles of the four frames

| Frame | Direction | Role | Required headers according to STOMP 1.2 |
|---|---|---|---|
| SEND | Client → Server | Sends a message to a destination | destination |
| SUBSCRIBE | Client → Server | Subscribes to receive messages from a destination | id, destination |
| UNSUBSCRIBE | Client → Server | Cancels a subscription that was registered | id |
| MESSAGE | Server → Client | Delivers a message to the client through a subscription | destination, message-id, subscription |

A client can both send SEND and register SUBSCRIBE on the same connection. The server uses MESSAGE to deliver matching messages to the registered subscriptions.

Do not confuse MESSAGE with a command that the client sends to the server. It is a server-side frame, usually produced when the broker delivers a message to a subscription.

## 3. SEND: sending a message to a destination

SEND puts a message into the messaging system. The required header is destination; the body contains the content to send.

Text sending example:

~~~text
SEND
destination:/queue/orders
content-type:text/plain
content-length:8

ORD-1001^@
~~~

JSON sending example:

~~~text
SEND
destination:/queue/orders
content-type:application/json
event-type:OrderCreated
correlation-id:checkout-9001

{"orderId":"ORD-1001","status":"CREATED"}^@
~~~

In the second example:

- destination chooses where the message is received.
- content-type indicates that the body is JSON.
- event-type and correlation-id are application headers defined by the application itself.
- The body contains the business data.

### A destination is a string interpreted by the server

The STOMP specification treats a destination as an opaque string. The protocol itself does not require that /queue/orders have point-to-point semantics or that /topic/orders must broadcast.

Many brokers use the convention:

- /queue/...: usually point-to-point.
- /topic/...: usually publish-subscribe.

This is a common convention, not a general guarantee of STOMP. The destination syntax, access permissions, durability, routing, and delivery semantics depend on the broker or STOMP server in use.

### Additional headers, transaction, and receipt

SEND can contain headers defined by the application. The server must forward these user-defined headers in the corresponding MESSAGE frame, in addition to the server's own headers that it adds.

SEND also supports the transaction header to attach the send operation to a STOMP transaction opened with BEGIN. When you need the server to confirm it has processed the frame, the client can add the receipt header; the server can return a RECEIPT frame if it supports it.

If the server cannot process SEND, according to STOMP 1.2 the server sends ERROR and then closes the connection. The application should handle both protocol errors and transport errors on the client.

## 4. SUBSCRIBE: registering to receive messages

SUBSCRIBE asks the server to register the client to receive messages from a destination. Two required headers:

- destination: where the client wants to listen.
- id: the subscription identifier.

Example:

~~~text
SUBSCRIBE
id:orders-live
destination:/topic/orders
ack:auto

^@
~~~

After registration, the messages that the broker routes to the subscription are sent back to the client as MESSAGE frames.

### Subscription ID

A STOMP connection can open multiple subscriptions, including multiple subscriptions to the same destination. Therefore:

- Each SUBSCRIBE must have an id.
- The ids must be different within the same connection.
- The server uses the id to fill in the subscription header in the MESSAGE frame.
- The client uses that same id when sending UNSUBSCRIBE.

Example of the same connection registering two subscriptions:

~~~text
SUBSCRIBE
id:orders-all
destination:/topic/orders

^@

SUBSCRIBE
id:orders-priority
destination:/topic/orders
ack:client-individual

^@
~~~

The two subscriptions can receive messages from the same destination but have their own IDs and acknowledgement policies. If the server supports selectors or other subscription options, they are usually passed through the broker's own headers; check the broker documentation because those headers are not necessarily part of standard STOMP.

### ack mode: auto, client, and client-individual

The ack header controls how the client acknowledges that it has processed a message. If omitted, the default is auto.

| Mode | How it works | Consequence |
|---|---|---|
| auto | The client does not need to send ACK; the server considers the message received when it is sent to the client | Simple, but a message can be lost if the client fails before finishing processing |
| client | The client sends ACK or NACK; the acknowledgement is cumulative | ACKing one message acknowledges all earlier messages on the subscription as well |
| client-individual | The client sends ACK or NACK for each message | Independent acknowledgement, suitable for parallel processing or out-of-order completion |

With client and client-individual, the server does not consider the message consumed until it receives the ACK. If the connection is lost before the ACK, the server can redeliver the message. The final behavior on NACK—delivering to another consumer, discarding the message, or putting it into a dead-letter queue—depends on the broker.

### Which header does ACK use?

With STOMP 1.2, if a subscription requires explicit acknowledgement, the MESSAGE frame must have an ack header. This value is a token for the client to use in an ACK or NACK frame.

Example MESSAGE:

~~~text
MESSAGE
subscription:orders-priority
message-id:msg-9001
ack:ack-token-9001
destination:/topic/orders
content-type:application/json

{"orderId":"ORD-1001","status":"CREATED"}^@
~~~

The client acknowledges with:

~~~text
ACK
id:ack-token-9001

^@
~~~

The id header of the ACK frame must match the value of ack in the MESSAGE frame. Do not use message-id in place of ack: the two headers have different roles.

If the client cannot process the message, it can send:

~~~text
NACK
id:ack-token-9001

^@
~~~

NACK tells the server that the client did not consume the message successfully. How the broker retries, moves the message, or puts it into a DLQ is implementation-specific.

## 5. UNSUBSCRIBE: canceling a subscription

UNSUBSCRIBE ends an existing subscription. The required header is id, which must exactly match the ID used when SUBSCRIBE was sent.

~~~text
UNSUBSCRIBE
id:orders-live

^@
~~~

After the server processes the cancellation, the connection no longer receives messages through that subscription.

Notes:

- There is no need to send the destination again; the server identifies the subscription by id.
- If the connection has multiple subscriptions, canceling one ID does not cancel the remaining subscriptions.
- Using a non-existent ID or an ID that does not belong to the current connection can cause the server to report an error.
- You can add a receipt to request confirmation that the server has processed the cancel frame, if the server supports it.

Example:

~~~text
UNSUBSCRIBE
id:orders-live
receipt:unsubscribe-42

^@
~~~

The server can return:

~~~text
RECEIPT
receipt-id:unsubscribe-42

^@
~~~

RECEIPT confirms that the corresponding frame has been processed by the server. It is not proof that the final business message has been fully processed by a consumer.

## 6. MESSAGE: the server delivers a message to a subscription

MESSAGE is the frame the server sends to the client when a message is delivered through a subscription. According to STOMP 1.2, the three required headers are:

- destination: the source destination of the message.
- message-id: the unique ID of the message supplied by the server.
- subscription: the ID of the subscription that receives the message.

If the subscription uses ack:auto, the ack header is not required. If it uses ack:client or ack:client-individual, the frame must additionally have an ack token.

Example:

~~~text
MESSAGE
destination:/topic/orders
message-id:msg-9001
subscription:orders-live
content-type:application/json
event-type:OrderCreated

{"orderId":"ORD-1001","status":"CREATED"}^@
~~~

The client uses the subscription header to know which registration the message came from. This is important when one connection has multiple subscriptions to the same destination or subscriptions that use different acknowledgement modes.

### The server does not send MESSAGE arbitrarily

According to STOMP, the server does not send spontaneous messages to an arbitrary client. A message the server sends must be tied to a specific subscription, and the subscription header must match the ID in the original SUBSCRIBE frame.

The broker can add the server's own headers. The user-defined headers from the SEND frame are also forwarded in the MESSAGE frame. Therefore, a consumer can receive both the metadata sent by the producer and the metadata created by the broker.

## 7. The complete lifecycle: SEND → MESSAGE → ACK → UNSUBSCRIBE

Consider a client that subscribes to receive orders, a producer that sends an event, a broker that delivers the message, and a consumer that acknowledges after processing:

~~~text
Client                                      STOMP Server / Broker
  |                                                   |
  |---- SUBSCRIBE id:orders-1 ----------------------->|
  |     destination:/queue/orders                     |
  |     ack:client-individual                         |
  |                                                   |
  |<--- RECEIPT (if requested and supported) ---------|
  |                                                   |
  |<--- MESSAGE --------------------------------------|
  |     subscription:orders-1                         |
  |     message-id:msg-101                            |
  |     ack:ack-101                                   |
  |     destination:/queue/orders                    |
  |     body: OrderCreated                            |
  |                                                   |
  |---- ACK id:ack-101 ------------------------------>|
  |                                                   |
  |---- UNSUBSCRIBE id:orders-1 --------------------->|
  |                                                   |
~~~

The flow proceeds as follows:

1. The client sends SUBSCRIBE with the ID orders-1.
2. The broker stores the subscription and routes matching messages to it.
3. The server sends a MESSAGE frame; the subscription header indicates which subscription the message belongs to.
4. Because client-individual is used, the client finishes processing the message and then sends ACK with the token from the ack header.
5. The client sends UNSUBSCRIBE with the original ID when it no longer wants to receive messages.

If the processing step fails, the client can send NACK. If the client disconnects before the ACK, the broker can redeliver according to its delivery policy. Therefore, the application should still handle duplicates safely when the broker supports redelivery.

## 8. How do RECEIPT, ACK, and MESSAGE differ?

Three concepts that are often confused:

| Component | Meaning | What it does not prove |
|---|---|---|
| RECEIPT | The server has processed a client frame that requested a receipt | Does not prove that the business handler has completed or that a consumer has processed the message |
| MESSAGE | The server is delivering a message to a subscription | Does not by itself prove that the client has finished processing |
| ACK | The client confirms it has consumed the message according to the ack mode | Is not a confirmation that the producer sent the message successfully |

A client can add the receipt header to a SEND, SUBSCRIBE, or UNSUBSCRIBE frame to request a receipt. The server returns RECEIPT with a receipt-id matching that value.

Because STOMP transmits frames as a stream, a receipt also confirms that the earlier frames have been received by the server. However, the earlier frames may not have finished processing. Therefore, if you need business confirmation, design a separate response/event with a correlation ID instead of treating a receipt as the business processing result.

## 9. SEND and SUBSCRIBE in Spring STOMP over WebSocket

Spring supports STOMP over WebSocket through the two modules spring-messaging and spring-websocket. When STOMP message broker support is enabled, Spring receives frames from the WebSocket, converts them into a Spring Message<?>, and puts them into the internal message channel.

Basic configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // HTTP/WebSocket handshake endpoint.
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        // SEND to /app/... is routed to @MessageMapping.
        registry.setApplicationDestinationPrefixes("/app");

        // SUBSCRIBE and SEND to these prefixes are handled by the broker.
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Two types of destination with commonly seen roles:

- /app: the application prefix; the client sends SEND here to invoke an @MessageMapping controller.
- /topic and /queue: the broker prefixes; the client usually SUBSCRIBEs here to receive broadcast or queue messages.

In Spring, the prefixes above are the application's routing configuration. They are not general rules of the STOMP protocol.

### SEND to @MessageMapping

Controller:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders")
    @SendTo("/topic/order-events")
    public OrderEvent createOrder(OrderCommand command) {
        // Perform validation and business processing.
        return new OrderEvent(
                command.orderId(),
                "CREATED"
        );
    }
}

public record OrderCommand(String orderId) {}

public record OrderEvent(String orderId, String status) {}
~~~

The client sends:

~~~text
SEND
destination:/app/orders
content-type:application/json

{"orderId":"ORD-1001"}^@
~~~

Spring strips the /app prefix, routes the /orders part to @MessageMapping("/orders"), converts the JSON payload into an OrderCommand using a suitable message converter, and invokes the controller.

The return value is converted into a Spring Message and then sent through the brokerChannel. With @SendTo("/topic/order-events"), the broker emits the message to the subscriptions that match the destination. The client receives a MESSAGE frame over the WebSocket.

### SUBSCRIBE to the broker

The client subscribes:

~~~text
SUBSCRIBE
id:order-events-ui
destination:/topic/order-events
ack:auto

^@
~~~

This frame is put into the clientInboundChannel and passed to the broker to store the subscription. When a controller or a server component sends a message to /topic/order-events, the broker finds the matching subscribers and emits a MESSAGE frame through the clientOutboundChannel.

### MESSAGE from the server to the client

You can proactively send a message from a service using SimpMessagingTemplate:

~~~java
@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderEvent event) {
        messagingTemplate.convertAndSend("/topic/order-events", event);
    }
}
~~~

The broker forwards the payload to the matching subscriptions and Spring encodes it into a STOMP MESSAGE frame on the WebSocket connection.

### A one-time SUBSCRIBE with @SubscribeMapping

@SubscribeMapping handles a subscribe frame by application destination. By default, the return value is sent directly to the client that subscribed through the clientOutboundChannel, and is not sent to the broker for broadcast.

This is useful when the UI needs to load an initial snapshot, for example the current order state. After the snapshot, the client can still subscribe to /topic/order-events to receive subsequent updates.

Do not confuse @SubscribeMapping with a long-lived broker subscription: by default the response is only a reply to that one subscribe.

## 10. Destination, broker, and broker relay

Spring can use a simple in-memory broker or relay to an external STOMP broker.

The **simple broker** stores subscriptions in the memory of the Spring application and emits messages to the matching subscribers. It is suitable for simple cases, but does not provide all the features of a dedicated message broker.

The **broker relay** maintains a TCP connection from Spring to an external STOMP broker such as RabbitMQ or ActiveMQ. Spring forwards frames up to the broker and forwards the frames the broker returns down to the WebSocket clients.

Some points to determine per broker:

- Destination naming rules.
- Queue/topic semantics and durability.
- Selectors or broker-specific headers.
- Acknowledgement, redelivery, and dead-letter behavior.
- Transaction and receipt support.
- Maximum frame size and header limits.

Do not assume that a destination or a broker-specific header will work the same on every STOMP server.

## 11. Encoding rules and common mistakes

STOMP 1.2 has important encoding rules:

- Command and header names are case-sensitive.
- Header values must not be arbitrarily trimmed or padded with whitespace by the server/client.
- For frames other than CONNECT and CONNECTED, header values need to escape the special characters: \r, \n, \c for the colon, and \\ for the backslash.
- content-length counts bytes, not characters.
- If the body contains a NULL byte, content-length must be present.
- If a header appears multiple times, STOMP 1.2 recommends using the first value.

Common mistakes:

1. **Sending SEND without a destination.** The server does not know where to route the message; the frame is invalid and the server may return ERROR and then close the connection.
2. **Sending SUBSCRIBE without an id.** Each subscription needs a unique ID within the connection.
3. **Reusing a subscription ID within the same connection.** The server cannot distinguish the subscriptions.
4. **UNSUBSCRIBE using the destination instead of the id.** STOMP 1.2 requires the ID of the subscription that was created.
5. **Thinking that MESSAGE is a frame the client sends.** It is a frame the server sends to the client by subscription.
6. **Confusing message-id with the ack token.** ACK/NACK use the value of the ack header of MESSAGE.
7. **Leaving ack:auto for important processing without accepting the risk of losing messages.** For explicit ack, choose client or client-individual according to the processing and completion order.
8. **Assuming that client ack is always independent.** client is cumulative; only client-individual acknowledges each message.
9. **Treating a receipt as business success.** A receipt confirms that the server has processed the frame at the protocol layer.
10. **Assuming /queue and /topic have standard semantics.** STOMP leaves the destination semantics for the server to decide.
11. **Using content-length as a character count.** With UTF-8 or binary, you need to calculate the number of bytes.
12. **Sending a header value that contains a newline or colon without escaping.** The parser may interpret the frame structure incorrectly.
13. **Keeping unnecessary subscriptions.** Cancel with UNSUBSCRIBE when the UI leaves the screen or no longer needs to receive data.
14. **Not handling ERROR and connection loss.** The client needs to observe both the STOMP ERROR frame and WebSocket/transport errors.

## 12. Testing checklist

- [ ] Connect over STOMP and negotiate the correct protocol version.
- [ ] Send SEND with a valid destination and a body with the correct content type.
- [ ] Check whether user-defined headers are preserved in MESSAGE.
- [ ] Register multiple subscriptions with different IDs.
- [ ] Check that MESSAGE.subscription matches the registered ID.
- [ ] Test ack:auto, ack:client, and ack:client-individual.
- [ ] Confirm that ACK uses the token from the ack header, not message-id by mistake.
- [ ] Send NACK and observe the broker's redelivery/DLQ behavior.
- [ ] Cancel the correct subscription with UNSUBSCRIBE id.
- [ ] Check receipts if the broker supports them.
- [ ] Test UTF-8 payloads, binary payloads, and a body with a NULL byte.
- [ ] Confirm that Spring routes /app to @MessageMapping, and /topic and /queue to the broker.
- [ ] Test both the simple broker and the broker relay if the application supports both modes.
- [ ] Handle ERROR frames, timeouts, and WebSocket disconnects.

## 13. Conclusion

SEND puts a message into a destination; SUBSCRIBE creates a subscription to receive messages with a unique ID; UNSUBSCRIBE ends that subscription; MESSAGE is the frame the server sends back to the client through a specific subscription. The destination header identifies where to send to or the source of the message, subscription links MESSAGE to SUBSCRIBE, and the ack token links MESSAGE to ACK/NACK when using explicit acknowledgement. In Spring STOMP over WebSocket, SEND to the /app prefix is routed to @MessageMapping, while subscriptions to a broker prefix such as /topic are stored and served by the broker. Always check the destination semantics, acknowledgement, and receipt against the broker you are actually deploying.

## Official references

- [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html) — frame grammar, SEND, SUBSCRIBE, UNSUBSCRIBE, MESSAGE, ACK/NACK, receipt, and header rules.
- [Spring Framework 7.0.10 Reference: STOMP Overview](https://www.springframework.org/spring/reference/web/websocket/stomp/overview.html) — STOMP frame model, destination, Spring broker, and broker relay.
- [Spring Framework 7.0.10 Reference: Flow of Messages](https://springframework.org/spring-framework/reference/web/websocket/stomp/message-flow.html) — clientInboundChannel, brokerChannel, clientOutboundChannel, @MessageMapping, and broker routing.
- [Spring Framework 7.0 Reference: Annotated Controllers](https://www.springframework.org/spring/reference/7.0/web/websocket/stomp/handle-annotations.html) — @MessageMapping, @SubscribeMapping, @SendTo, and return values.
- [Spring Framework 7.0 Reference: Enable STOMP](https://www.springframework.org/spring/reference/7.0/web/websocket/stomp/enable.html) — registering the WebSocket STOMP endpoint and configuring destination prefixes.
